"""Adversarial stress test suite for Milestone 1 (Multi-Agent Trading Architecture Integration).

Authored by teamwork_challenger_m1_2.
Verifies:
1. Crypto asset behavior and Fundamentals Analyst pruning / injection.
2. TraderProposal numerical validity (NaN, Infinity, float sanitization).
3. JevAdapter determinism and safety boundary behavior.
4. Reflection memory settlement under extreme price swings (+500%, -90%).
"""

import json
import math
import tempfile
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from core.agents import schemas
from core.agents.jev_adapter import JevAdapter
from core.agents.researchers.bear_researcher import create_bear_researcher
from core.agents.researchers.bull_researcher import create_bull_researcher
from core.agents.schemas import TraderAction, TraderProposal
from core.graph.trading_graph import TradingAgentsGraph
from core.memory.log import TradingMemoryLog
from core.memory.reflection import Reflector


class MockChatModel(BaseChatModel):
    """Deterministic mock chat model recording invocations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._calls = []

    @property
    def _llm_type(self) -> str:
        return "mock_chat"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._calls.append(messages)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Report analysis.\n\n**Rating**: Buy\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
                    )
                )
            ]
        )

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        def _produce(_):
            if schema == schemas.ResearchPlan:
                return schemas.ResearchPlan(
                    recommendation=schemas.PortfolioRating.BUY,
                    rationale="Sound growth",
                    strategic_actions="Accumulate",
                )
            elif schema == schemas.TraderProposal:
                return schemas.TraderProposal(
                    action=schemas.TraderAction.BUY,
                    reasoning="Breakout above resistance",
                    entry_price=65000.0,
                    stop_loss=62000.0,
                    symbol="BTC-USD",
                )
            elif schema == schemas.PortfolioDecision:
                return schemas.PortfolioDecision(
                    rating=schemas.PortfolioRating.BUY,
                    executive_summary="Favorable",
                    investment_thesis="Long-term thesis",
                )
            return None

        return RunnableLambda(_produce)


# ---------------------------------------------------------------------------
# 1. TraderProposal Numerical Integrity & Sanitization Tests
# ---------------------------------------------------------------------------


def test_trader_proposal_numerical_leakage_nan():
    """TraderProposal must coerce NaN to None and serialize to valid RFC 8259 JSON."""
    p_float_nan = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Test proposal",
        entry_price=float("nan"),
        stop_loss=100.0,
        symbol="BTC-USD",
    )
    assert p_float_nan.entry_price is None

    p_str_nan = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Test proposal",
        entry_price="nan",
        stop_loss=100.0,
        symbol="BTC-USD",
    )
    assert p_str_nan.entry_price is None

    # Strict JSON serialization now succeeds
    dumped = json.dumps(p_float_nan.model_dump(), allow_nan=False)
    assert '"entry_price": null' in dumped


def test_trader_proposal_numerical_leakage_infinity():
    """TraderProposal must coerce Infinity to None and serialize cleanly."""
    p_inf = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Test proposal",
        entry_price=float("inf"),
        stop_loss=100.0,
        symbol="ETH-USD",
    )
    assert p_inf.entry_price is None

    p_str_inf = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Test proposal",
        entry_price="Infinity",
        stop_loss=100.0,
        symbol="ETH-USD",
    )
    assert p_str_inf.entry_price is None

    dumped = json.dumps(p_inf.model_dump(), allow_nan=False)
    assert '"entry_price": null' in dumped


def test_trader_proposal_string_range_coercion():
    """Verify that string ranges (e.g. '150-160') are correctly coerced to None."""
    p_range = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Test proposal",
        entry_price="150-160",
        stop_loss="90-100",
        symbol="SOL-USD",
    )
    assert p_range.entry_price is None
    assert p_range.stop_loss is None


# ---------------------------------------------------------------------------
# 2. JevAdapter Safety Checks & NaN Bypass Vulnerability
# ---------------------------------------------------------------------------


def test_jev_adapter_nan_bypass_exploit():
    """Security/Safety test: JevAdapter.score_trader_proposal strictly rejects NaN entry prices."""
    jev = JevAdapter()
    # Case A: Dict with raw NaN
    score_raw = jev.score_trader_proposal({
        "action": "Buy",
        "reasoning": "Exploit proposal",
        "entry_price": float("nan"),
        "stop_loss": 50.0,
        "symbol": "BTC-USD",
    })
    assert score_raw["stop_valid"] is False
    assert score_raw["approved"] is False

    # Case B: Proposal with sanitized entry_price (None) and stop_loss (50.0)
    p_nan = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Exploit proposal",
        entry_price=float("nan"),
        stop_loss=50.0,
        symbol="BTC-USD",
    )
    score_p = jev.score_trader_proposal(p_nan)
    assert score_p["stop_valid"] is False
    assert score_p["approved"] is False


def test_jev_adapter_stop_loss_rules():
    """Verify standard stop-loss ordering for Buy and Sell."""
    jev = JevAdapter()

    # Buy: stop must be below entry
    p_buy_ok = TraderProposal(
        action=TraderAction.BUY, reasoning="Good", entry_price=100.0, stop_loss=90.0, symbol="BTC-USD"
    )
    assert jev.score_trader_proposal(p_buy_ok)["stop_valid"] is True

    p_buy_bad = TraderProposal(
        action=TraderAction.BUY, reasoning="Bad", entry_price=100.0, stop_loss=110.0, symbol="BTC-USD"
    )
    assert jev.score_trader_proposal(p_buy_bad)["stop_valid"] is False
    assert jev.score_trader_proposal(p_buy_bad)["approved"] is False

    # Sell: stop must be above entry
    p_sell_ok = TraderProposal(
        action=TraderAction.SELL, reasoning="Good", entry_price=100.0, stop_loss=110.0, symbol="BTC-USD"
    )
    assert jev.score_trader_proposal(p_sell_ok)["stop_valid"] is True

    p_sell_bad = TraderProposal(
        action=TraderAction.SELL, reasoning="Bad", entry_price=100.0, stop_loss=90.0, symbol="BTC-USD"
    )
    assert jev.score_trader_proposal(p_sell_bad)["stop_valid"] is False
    assert jev.score_trader_proposal(p_sell_bad)["approved"] is False


def test_jev_adapter_determinism_100_runs():
    """Verify JevAdapter decision consistency across 100 runs."""
    jev = JevAdapter()
    p = TraderProposal(
        action=TraderAction.BUY,
        reasoning="Solid support bounce",
        entry_price=65000.0,
        stop_loss=62000.0,
        symbol="BTC-USD",
    )
    runs = [jev.score_trader_proposal(p) for _ in range(100)]
    first = runs[0]
    assert all(r == first for r in runs), "JevAdapter score_trader_proposal is non-deterministic!"

    variants = {
        "v1": {"action": "Buy", "risk": "Aggressive scalp"},
        "v2": {"action": "Hold", "risk": "Wait for confirmation"},
    }
    variant_runs = [jev.pick_variant("Crypto breakout", variants) for _ in range(100)]
    assert all(v == variant_runs[0] for v in variant_runs), "JevAdapter pick_variant is non-deterministic!"


# ---------------------------------------------------------------------------
# 3. Crypto Fundamentals Pruning & Stale Statement Injection
# ---------------------------------------------------------------------------


def test_crypto_debate_stale_fundamentals_injection():
    """Vulnerability test: Stale corporate financial statements in state['fundamentals_report']

    must not leak into crypto deliberations.
    """
    stale_text = "STALE SEC 10-K: Revenue $95B, EBITDA margin 32%, PE 28"
    captured_prompts = []

    class MockPromptCapturingLLM(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "capturing_mock"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            captured_prompts.append(messages)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Thesis"))])

    llm = MockPromptCapturingLLM()
    bull_node = create_bull_researcher(llm)
    bear_node = create_bear_researcher(llm)

    state = {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "instrument_context": "Bitcoin crypto asset",
        "market_report": "BTC market structure",
        "sentiment_report": "Bullish sentiment",
        "news_report": "ETF inflows",
        "fundamentals_report": stale_text,
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
    }

    bull_node(state)
    prompt_str = str(captured_prompts[0])
    assert stale_text not in prompt_str, "Stale corporate financial statements must NEVER leak into Bull prompt"
    assert "Asset fundamentals: Not applicable" in prompt_str

    captured_prompts.clear()
    bear_node(state)
    prompt_str_bear = str(captured_prompts[0])
    assert stale_text not in prompt_str_bear, "Stale corporate financial statements must NEVER leak into Bear prompt"
    assert "Asset fundamentals: Not applicable" in prompt_str_bear


def test_crypto_graph_execution_prunes_fundamentals(monkeypatch):
    """TradingAgentsGraph dynamically prunes Fundamentals Analyst
    when propagate() is called with asset_type='crypto'.
    """
    executed_nodes = []

    class MockExecutionLLM(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "exec_mock"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            msg_str = str(messages)
            if "fundamental information" in msg_str:
                executed_nodes.append("Fundamentals Analyst")
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="Report.\n\n**Rating**: Buy\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
                        )
                    )
                ]
            )

        def bind_tools(self, tools, **kwargs):
            return self

        def with_structured_output(self, schema, **kwargs):
            return RunnableLambda(lambda _: None)

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {
            "results_dir": str(Path(tmpdir) / "results"),
            "data_cache_dir": str(Path(tmpdir) / "cache"),
            "memory_log_path": str(Path(tmpdir) / "log.md"),
            "llm_provider": "mock",
            "checkpoint_enabled": False,
            "max_tool_rounds": 1,
            "max_recur_limit": 50,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }

        import core.graph.trading_graph as tg_module

        class _MockClient:
            def __init__(self, *a, **k):
                pass

            def get_llm(self):
                return MockExecutionLLM()

        monkeypatch.setattr(tg_module, "create_tier_client", _MockClient)

        graph = TradingAgentsGraph(config=cfg)
        assert "Fundamentals Analyst" in graph.workflow.nodes, "Fundamentals Analyst present in stock workflow"

        # When propagate is called with asset_type="crypto", the graph prunes Fundamentals Analyst
        graph.propagate("BTC-USD", "2026-04-18", asset_type="crypto")
        assert "Fundamentals Analyst" not in executed_nodes, (
            "Fundamentals Analyst must NOT execute for crypto assets"
        )


# ---------------------------------------------------------------------------
# 4. Reflection Memory Settlement Against Extreme Swings (+500%, -90%)
# ---------------------------------------------------------------------------


def test_reflection_memory_extreme_price_swings():
    """Verify memory log update, tag encoding, and reflection prompt with +500% and -90% returns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test_memory.md"
        mem_log = TradingMemoryLog({"memory_log_path": str(log_path)})

        mock_llm = MockChatModel()
        reflector = Reflector(mock_llm)

        # 1. Store and settle +500% gain (BTC-USD)
        mem_log.store_decision("BTC-USD", "2026-04-18", "Buy BTC breakout", rating="Buy")
        ok_500 = mem_log.update_with_outcome(
            ticker="BTC-USD",
            trade_date="2026-04-18",
            raw_return=5.0,  # +500.0%
            alpha_return=4.8,  # +480.0%
            holding_days=5,
            reflection="Massive bull market run: thesis verified.",
            resolution_date="2026-04-25",
        )
        assert ok_500 is True

        # 2. Store and settle -90% crash (SOL-USD)
        mem_log.store_decision("SOL-USD", "2026-04-18", "Buy SOL at resistance", rating="Buy")
        ok_neg90 = mem_log.update_with_outcome(
            ticker="SOL-USD",
            trade_date="2026-04-18",
            raw_return=-0.90,  # -90.0%
            alpha_return=-0.95,  # -95.0%
            holding_days=5,
            reflection="Flash liquidity drain: stop-loss executed.",
            resolution_date="2026-04-25",
        )
        assert ok_neg90 is True

        # 3. Verify parse round-trip
        entries = mem_log.load_entries()
        assert len(entries) == 2
        assert entries[0]["raw"] == "+500.0%"
        assert entries[0]["alpha"] == "+480.0%"
        assert entries[1]["raw"] == "-90.0%"
        assert entries[1]["alpha"] == "-95.0%"

        # 4. Verify past context generation
        btc_ctx = mem_log.get_past_context("BTC-USD")
        assert "+500.0%" in btc_ctx
        assert "-90.0%" in btc_ctx  # Included in cross-ticker lessons
