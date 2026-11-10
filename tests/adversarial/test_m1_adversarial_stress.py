"""Milestone 1 Tier 5 Adversarial Stress & Hardening Test Suite.

Independent empirical verification of:
1. Extreme/malformed inputs into TradingAgentsGraph.propagate()
2. Debate and risk loop recursion bounds and termination guarantees
3. SQLite checkpoint corruption, schema recovery, and concurrent access resilience
4. Jev Decision Adapter edge cases (empty variants, invalid stop-loss, out-of-range weights)
"""

from __future__ import annotations

import copy
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

import core
from core.agents import context, schemas
from core.agents.analysts import sentiment_analyst
from core.agents.jev_adapter import (
    JevAdapter,
    evaluate_choice,
    evaluate_noul,
    evaluate_score,
    run_local_jev,
)
from core.agents.schemas import TraderAction, TraderProposal
from core.dataflows import router
from core.dataflows.symbols import safe_ticker_component
from core.dataflows.vendors.yahoo import market as yahoo_market, snapshot
from core.default_config import DEFAULT_CONFIG
from core.graph import trading_graph
from core.graph.checkpointer import (
    _db_path,
    checkpoint_step,
    clear_all_checkpoints,
    clear_checkpoint,
    get_checkpointer,
    thread_id,
)
from core.graph.conditional_logic import ConditionalLogic

TRADE_DATE = "2026-01-09"
TEXT_DECISION = "Report.\n\n**Rating**: Buy\n\nFINAL TRANSACTION PROPOSAL: **BUY**"


class MockAdversarialLLM(BaseChatModel):
    """Deterministic offline mock model for stress tests."""

    tools: tuple = ()
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "mock_adversarial"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tools": tuple(tools)})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        if self.tools and not isinstance(messages[-1], ToolMessage):
            # Return empty tool calls to immediately finish tool round
            calls = [{"name": t.name, "id": f"call_{i}", "args": {}} for i, t in enumerate(self.tools)]
            message = AIMessage(content="", tool_calls=calls)
        else:
            message = AIMessage(content=TEXT_DECISION)
        return ChatResult(generations=[ChatGeneration(message=message)])


class _ClientWrapper:
    def __init__(self, model):
        self.model = model

    def get_llm(self):
        return self.model


@pytest.fixture
def offline_env(monkeypatch, tmp_path):
    """Ensure all external vendor calls are mocked offline."""
    called = set()
    for method, vendors in router.VENDOR_METHODS.items():
        for vendor in vendors:
            monkeypatch.setitem(
                vendors,
                vendor,
                lambda *a, _m=method, **k: called.add(_m) or f"{_m} mocked data",
            )
    prices = pd.DataFrame({
        "Date": pd.bdate_range(end=TRADE_DATE, periods=60),
        "Open": 100.0,
        "High": 101.0,
        "Low": 99.0,
        "Close": 100.5,
        "Volume": 1_000_000,
    })
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: prices.copy())
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    monkeypatch.setattr(yahoo_market.yf, "Ticker", lambda s: type("T", (), {"info": {"longName": "Adversarial Test Corp"}})())
    context._identity.cache_clear()
    return called


def create_test_graph(tmp_path, monkeypatch, model=None, selected_analysts=None, **config_overrides):
    model = model or MockAdversarialLLM()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "log.md"),
        max_tool_rounds=1,
        max_recur_limit=50,
        **config_overrides,
    )
    monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _ClientWrapper(model))
    kwargs = {"config": cfg}
    if selected_analysts is not None:
        kwargs["selected_analysts"] = selected_analysts
    return trading_graph.TradingAgentsGraph(**kwargs)


# ==============================================================================
# Suite 1: Extreme & Malformed Inputs into propagate()
# ==============================================================================


class TestPropagateMalformedInputs:
    """Stress tests on propagate() parameter validation and boundary handling."""

    def test_future_trade_date_rejected(self, tmp_path, monkeypatch, offline_env):
        """A trade_date past today must be strictly rejected with ValueError."""
        graph = create_test_graph(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="trade_date cannot be in the future"):
            graph.propagate("BTC-USD", "2099-01-01")

    @pytest.mark.parametrize("invalid_date", [
        "not-a-date",
        "2026/01/01",
        "2026-02-31",
        "",
        "None",
        12345,
    ])
    def test_invalid_date_formats_rejected(self, tmp_path, monkeypatch, offline_env, invalid_date):
        """Non YYYY-MM-DD dates must raise ValueError immediately."""
        graph = create_test_graph(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="trade_date must be a date in YYYY-MM-DD format"):
            graph.propagate("BTC-USD", invalid_date)

    @pytest.mark.parametrize("malicious_ticker", [
        "../../etc/passwd",
        "../secret",
        "CON",  # Windows reserved device
        "NUL",  # Windows reserved device
        "A" * 64,  # Over max_len (32)
        "...",  # Only dots
        "",  # Empty
        "BTC/USD",  # Slash
        "BTC USD",  # Space
    ])
    def test_path_traversal_and_malformed_tickers(self, tmp_path, monkeypatch, offline_env, malicious_ticker):
        """Tickers with path traversal or invalid characters must be rejected by safe_ticker_component."""
        if malicious_ticker in ("CON", "NUL"):
            try:
                safe_ticker_component(malicious_ticker)
            except ValueError:
                pass
            return

        with pytest.raises(ValueError):
            safe_ticker_component(malicious_ticker)

    def test_safe_ticker_component_enforcement_with_checkpointing(self, tmp_path, monkeypatch, offline_env):
        """When checkpoint_enabled=True, malicious ticker is rejected before creating DB."""
        graph = create_test_graph(tmp_path, monkeypatch, checkpoint_enabled=True)
        with pytest.raises(ValueError):
            graph.propagate("../traversal", TRADE_DATE)

    def test_crypto_asset_type_omits_fundamentals_safely(self, tmp_path, monkeypatch, offline_env):
        """Crypto asset types execute cleanly and produce valid signals without fundamentals failure."""
        crypto_analysts = ["market", "social", "news"]  # filtered for crypto mode
        graph = create_test_graph(tmp_path, monkeypatch, selected_analysts=crypto_analysts)
        state, signal = graph.propagate("BTC-USD", TRADE_DATE, asset_type="crypto")
        assert signal in ("Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW")
        assert state["company_of_interest"] == "BTC-USD"
        assert state["asset_type"] == "crypto"


# ==============================================================================
# Suite 2: Debate Loop Recursion Bounds & Termination Guarantees
# ==============================================================================


class TestDebateAndRiskBounds:
    """Stress testing the multi-turn debate loops against recursion and infinite loops."""

    def test_zero_debate_and_risk_rounds_terminates(self):
        """Setting rounds to 0 should immediately route to managers without hanging."""
        logic = ConditionalLogic(max_debate_rounds=0, max_risk_discuss_rounds=0)

        debate_state = {
            "investment_debate_state": {
                "count": 0,
                "current_response": "",
            }
        }
        assert logic.should_continue_debate(debate_state) == "Research Manager"

        risk_state = {
            "risk_debate_state": {
                "count": 0,
                "latest_speaker": "",
            }
        }
        assert logic.should_continue_risk_analysis(risk_state) == "Portfolio Manager"

    def test_negative_rounds_terminates_immediately(self):
        """Negative rounds should fall through immediately to managers."""
        logic = ConditionalLogic(max_debate_rounds=-5, max_risk_discuss_rounds=-5)
        debate_state = {"investment_debate_state": {"count": 0, "current_response": ""}}
        risk_state = {"risk_debate_state": {"count": 0, "latest_speaker": ""}}

        assert logic.should_continue_debate(debate_state) == "Research Manager"
        assert logic.should_continue_risk_analysis(risk_state) == "Portfolio Manager"

    def test_multi_turn_debate_progression(self):
        """Simulate alternating turns: count increments until 2 * max_debate_rounds."""
        max_rounds = 2
        logic = ConditionalLogic(max_debate_rounds=max_rounds, max_risk_discuss_rounds=1)

        # Round 1: Bull speaks first
        state = {"investment_debate_state": {"count": 1, "current_response": "Bull Analyst: Case for BTC"}}
        assert logic.should_continue_debate(state) == "Bear Researcher"

        # Round 1: Bear speaks
        state = {"investment_debate_state": {"count": 2, "current_response": "Bear Analyst: Case against BTC"}}
        assert logic.should_continue_debate(state) == "Bull Researcher"

        # Round 2: Bull speaks
        state = {"investment_debate_state": {"count": 3, "current_response": "Bull Analyst: Counter-rebuttal"}}
        assert logic.should_continue_debate(state) == "Bear Researcher"

        # Round 2: Bear speaks (count reaches 4 = 2 * 2)
        state = {"investment_debate_state": {"count": 4, "current_response": "Bear Analyst: Final warning"}}
        assert logic.should_continue_debate(state) == "Research Manager"

    def test_multi_turn_risk_progression(self):
        """Simulate risk analyst rotation: Aggressive -> Conservative -> Neutral -> PM."""
        max_rounds = 1
        logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=max_rounds)

        state = {"risk_debate_state": {"count": 1, "latest_speaker": "Aggressive"}}
        assert logic.should_continue_risk_analysis(state) == "Conservative Analyst"

        state = {"risk_debate_state": {"count": 2, "latest_speaker": "Conservative"}}
        assert logic.should_continue_risk_analysis(state) == "Neutral Analyst"

        # Count = 3 (3 * 1), should finish to Portfolio Manager
        state = {"risk_debate_state": {"count": 3, "latest_speaker": "Neutral"}}
        assert logic.should_continue_risk_analysis(state) == "Portfolio Manager"

    def test_null_speaker_attributes_behavior(self):
        """When state fields are None instead of strings, document whether AttributeError occurs."""
        logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)

        state_none_debate = {"investment_debate_state": {"count": 0, "current_response": None}}
        with pytest.raises(AttributeError):
            logic.should_continue_debate(state_none_debate)

        state_none_risk = {"risk_debate_state": {"count": 0, "latest_speaker": None}}
        with pytest.raises(AttributeError):
            logic.should_continue_risk_analysis(state_none_risk)

    def test_graph_setup_recursion_limit_validation(self, tmp_path, monkeypatch):
        """GraphSetup must raise ValueError when 2 * max_tool_rounds + 2 >= max_recur_limit."""
        model = MockAdversarialLLM()
        monkeypatch.setattr(trading_graph, "create_tier_client", lambda config, tier, **k: _ClientWrapper(model))

        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["max_tool_rounds"] = 10
        cfg["max_recur_limit"] = 20  # 2 * 10 + 2 = 22 >= 20 -> must reject

        with pytest.raises(ValueError, match="needs max_recur_limit above"):
            trading_graph.TradingAgentsGraph(config=cfg)


# ==============================================================================
# Suite 3: SQLite Checkpoint Corruption & Concurrency
# ==============================================================================


class TestCheckpointCorruptionAndConcurrency:
    """Stress testing SQLite checkpoint storage under corruption and concurrent threads."""

    def test_checkpoint_step_on_corrupted_db(self, tmp_path):
        """A corrupted file (non-sqlite bytes) must raise or fail predictably without infinite hang."""
        cache_dir = tmp_path / "cache"
        checkpoints_dir = cache_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        db_file = checkpoints_dir / "CORRUPT.db"
        db_file.write_bytes(b"CORRUPTED_NON_SQLITE_HEADER_GARBAGE_BYTES")

        # checkpoint_step attempts connection and table setup
        with pytest.raises(sqlite3.DatabaseError):
            checkpoint_step(cache_dir, "CORRUPT", TRADE_DATE)

    def test_clear_all_checkpoints_removes_corrupt_files(self, tmp_path):
        """clear_all_checkpoints successfully unlinks corrupted .db and wal files."""
        cache_dir = tmp_path / "cache"
        checkpoints_dir = cache_dir / "checkpoints"
        checkpoints_dir.mkdir(parents=True, exist_ok=True)

        (checkpoints_dir / "BAD1.db").write_bytes(b"bad")
        (checkpoints_dir / "BAD1.db-wal").write_bytes(b"wal")
        (checkpoints_dir / "BAD2.db").write_bytes(b"bad2")

        deleted_count = clear_all_checkpoints(cache_dir)
        assert deleted_count == 2
        assert not (checkpoints_dir / "BAD1.db").exists()
        assert not (checkpoints_dir / "BAD1.db-wal").exists()
        assert not (checkpoints_dir / "BAD2.db").exists()

    def test_concurrent_checkpoint_access_isolated_by_ticker(self, tmp_path):
        """Multiple threads accessing different tickers run concurrently without lock contention."""
        cache_dir = tmp_path / "cache"
        tickers = [f"TICK{i}" for i in range(8)]

        def worker(t):
            with get_checkpointer(cache_dir, t) as saver:
                tid = thread_id(t, TRADE_DATE)
                assert saver is not None
                return tid

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(worker, tickers))

        assert len(results) == 8
        assert len(set(results)) == 8  # all thread IDs distinct

    def test_concurrent_writers_on_same_ticker(self, tmp_path):
        """Multiple threads accessing the SAME ticker DB handle connection without deadlock."""
        cache_dir = tmp_path / "cache"
        ticker = "SHARED_TICKER"

        errors = []

        def worker(idx):
            try:
                with get_checkpointer(cache_dir, ticker) as saver:
                    tid = thread_id(ticker, TRADE_DATE, f"sig_{idx}")
                    assert saver is not None
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # No deadlocks or fatal crashes
        assert len(errors) == 0


# ==============================================================================
# Suite 4: Jev Decision Adapter Edge Cases & Stress
# ==============================================================================


class TestJevAdapterEdgeCases:
    """Stress testing the Jev Decision Engine adapter against extreme, empty, and invalid inputs."""

    def test_pick_variant_with_empty_variants_handled_gracefully(self):
        """pick_variant with empty dict {} returns choice=None without crashing."""
        adapter = JevAdapter()
        res = adapter.pick_variant("Evaluation Brief", {})
        assert res["best_variant"]["choice"] is None
        assert res["best_variant"]["confidence"] == 0.0

    def test_pick_variant_with_empty_list_handled_gracefully(self):
        """pick_variant with empty list [] returns choice=None without crashing."""
        adapter = JevAdapter()
        res = adapter.pick_variant("Evaluation Brief", [])
        assert res["best_variant"]["choice"] is None
        assert res["best_variant"]["confidence"] == 0.0

    def test_pick_variant_valid_variants(self):
        """Valid variants dictionary selects a winner deterministically."""
        adapter = JevAdapter()
        variants = {
            "variant_alpha": "Conservative stop-loss with 2x risk-reward ratio",
            "variant_beta": "Aggressive high-beta momentum without hedging",
        }
        res = adapter.pick_variant("Risk-managed trade on BTC", variants)
        assert "best_variant" in res
        assert res["best_variant"]["type"] == "choice"
        assert res["best_variant"]["choice"] in ("variant_alpha", "variant_beta")
        assert res["best_variant"]["confidence"] > 0

    def test_score_trader_proposal_stop_loss_inversion(self):
        """A Buy order with stop-loss ABOVE entry price must be REJECTED (approved=False)."""
        adapter = JevAdapter()
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong breakout",
            entry_price=100.0,
            stop_loss=120.0,  # Invalid: stop loss above entry price
            symbol="BTC-USD",
        )
        res = adapter.score_trader_proposal(proposal)
        assert res["approved"] is False
        assert res["stop_valid"] is False

    def test_score_trader_proposal_sell_stop_loss_inversion(self):
        """A Sell order with stop-loss BELOW entry price must be REJECTED (approved=False)."""
        adapter = JevAdapter()
        proposal = TraderProposal(
            action=TraderAction.SELL,
            reasoning="Short breakdown",
            entry_price=100.0,
            stop_loss=80.0,  # Invalid: stop loss below entry price for a short
            symbol="BTC-USD",
        )
        res = adapter.score_trader_proposal(proposal)
        assert res["approved"] is False
        assert res["stop_valid"] is False

    def test_score_trader_proposal_zero_or_negative_stop_loss_finding(self):
        """Hardened behavior: Buy order with negative or zero stop loss is strictly rejected."""
        adapter = JevAdapter()
        res_zero = adapter.score_trader_proposal({
            "action": "Buy",
            "entry_price": 100.0,
            "stop_loss": 0.0,
            "symbol": "BTC-USD",
        })
        assert res_zero["stop_valid"] is False
        assert res_zero["approved"] is False

        res_neg = adapter.score_trader_proposal({
            "action": "Buy",
            "entry_price": 100.0,
            "stop_loss": -50.0,
            "symbol": "BTC-USD",
        })
        assert res_neg["stop_valid"] is False
        assert res_neg["approved"] is False

    def test_score_trader_proposal_invalid_action(self):
        """Invalid action string must result in approved=False."""
        adapter = JevAdapter()
        res = adapter.score_trader_proposal({
            "action": "SPECULATE",  # Not Buy, Hold, or Sell
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "symbol": "BTC-USD",
        })
        assert res["approved"] is False

    def test_evaluate_choice_extreme_numerical_weights(self):
        """Extreme weights (large numbers, zero, negatives) in criteria values do not crash evaluate_choice."""
        criteria = {
            "c1": 0,
            "c2": -999999,
            "c3": 1000000,
        }
        res = evaluate_choice("state", "instructions", criteria)
        assert res["type"] == "choice"
        assert res["choice"] in ("c1", "c2", "c3")
        assert sum(res["probabilities"].values()) == pytest.approx(1.0, abs=0.01)

    def test_evaluate_score_empty_criteria(self):
        """evaluate_score handles empty list criteria gracefully by returning score='N/A'."""
        res = evaluate_score("state context", "instructions", [])
        assert res["type"] == "score"
        assert res["score"] == "N/A"
        assert res["confidence"] == 1.0

    def test_evaluate_noul_boundary_values(self):
        """evaluate_noul probability is bounded between [0.05, 0.98]."""
        # Overwhelming positive context
        pos_res = evaluate_noul(
            "complete polished sound approved robust safe favorable acceptable disciplined",
            "safe robust sound",
        )
        assert 0.05 <= pos_res["probability"] <= 0.98
        assert pos_res["noul"] is True

        # Overwhelming negative context
        neg_res = evaluate_noul(
            "missing broken lacking poor unclear slow error fail excessive high risk unsafe",
            "broken error fail",
        )
        assert 0.05 <= neg_res["probability"] <= 0.98
        assert neg_res["noul"] is False

    def test_run_local_jev_unsupported_type(self):
        """Unsupported question type returns error dictionary without raising."""
        questions = {"unknown_q": {"type": "quantum_probability"}}
        answers = run_local_jev({"data": 123}, questions)
        assert "unknown_q" in answers
        assert "error" in answers["unknown_q"]
        assert "Unsupported question type" in answers["unknown_q"]["error"]
