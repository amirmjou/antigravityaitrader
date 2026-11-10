"""Unit tests for Jev Decision Integration Adapter, Antigravity SDK client, and Interface Contracts."""

import pytest

from core import (
    JevAdapter,
    PortfolioDecision,
    PortfolioRating,
    TraderAction,
    TraderProposal,
)
from core.llm_clients.antigravity_client import (
    AntigravityClient,
    create_antigravity_trading_hierarchy,
)
from core.llm_clients.factory import create_llm_client


@pytest.mark.unit
class TestJevDecisionAdapter:
    """Verifies deterministic offline heuristic engine and strategy variant scoring."""

    def test_jev_status(self):
        adapter = JevAdapter()
        status = adapter.status()
        assert status["mode"] == "on-premise-offline"
        assert status["provider"] == "local_heuristic_engine"
        assert status["api_key_required"] is False
        assert status["status"] == "ready"
        assert "noul" in status["supported_types"]

    def test_jev_decide_noul(self):
        adapter = JevAdapter()
        state = {"order": "Buy BTC-USD with stop-loss at 85000", "status": "safe and robust"}
        questions = {
            "is_safe": {
                "type": "noul",
                "instructions": "Is the order execution safe and robust?",
            }
        }
        res = adapter.decide(state, questions)
        assert "is_safe" in res
        assert res["is_safe"]["type"] == "noul"
        assert isinstance(res["is_safe"]["noul"], bool)
        assert res["is_safe"]["noul"] is True
        assert res["is_safe"]["probability"] >= 0.5

    def test_jev_decide_choice(self):
        adapter = JevAdapter()
        state = {"thesis": "Aggressive expansion and high momentum growth"}
        questions = {
            "posture": {
                "type": "choice",
                "instructions": "Which posture matches the thesis?",
                "criteria": {
                    "aggressive": "Aggressive momentum and high growth focus",
                    "defensive": "Capital preservation and conservative hedging",
                },
            }
        }
        res = adapter.decide(state, questions)
        assert res["posture"]["type"] == "choice"
        assert res["posture"]["choice"] == "aggressive"
        assert res["posture"]["confidence"] > 0.5

    def test_jev_decide_score(self):
        adapter = JevAdapter()
        state = {"metrics": "Clean, consistent, robust and favorable risk-reward"}
        questions = {
            "quality": {
                "type": "score",
                "instructions": "Overall quality of risk mitigation",
                "criteria": ["Poor", "Weak", "Acceptable", "Good", "Excellent"],
            }
        }
        res = adapter.decide(state, questions)
        assert res["quality"]["type"] == "score"
        assert res["quality"]["score"] in ("Good", "Excellent", "Acceptable")
        assert "probabilities" in res["quality"]

    def test_jev_pick_variant(self):
        adapter = JevAdapter()
        brief = "Select the optimal trading execution strategy for volatile crypto market"
        variants = {
            "var_market": "Immediate 100% market order without stop",
            "var_scaled": "Scaled limit orders with 2% stop-loss protection and risk hedge",
            "var_passive": "Wait for 20% drawdown before entering",
        }
        res = adapter.pick_variant(brief, variants)
        assert "best_variant" in res
        assert res["best_variant"]["choice"] in ("var_scaled", "var_market", "var_passive")
        assert "probabilities" in res["best_variant"]

    def test_jev_review_design_quality_gate(self):
        adapter = JevAdapter()
        brief = "Dark theme trading terminal with candle charts, order book, and execution controls"
        design = (
            "Clean visual hierarchy, high contrast green/red indicators, responsive layout, "
            "clear order submission button with confirmation dialog."
        )
        res = adapter.review_design(brief, design)
        assert "brand_fit" in res
        assert "visual_quality" in res
        assert "clarity" in res
        assert "cta_strength" in res
        assert "ready_to_ship" in res
        assert res["ready_to_ship"]["type"] == "noul"

    def test_score_trader_proposal_approved(self):
        adapter = JevAdapter()
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong momentum confirmed by RSI and MACD crossing above signal line.",
            entry_price=92000.0,
            stop_loss=88500.0,
            position_sizing="5% of portfolio",
            symbol="BTC-USD",
        )
        score_res = adapter.score_trader_proposal(proposal)
        assert score_res["approved"] is True
        assert score_res["stop_valid"] is True
        assert score_res["action"] == "Buy"

    def test_score_trader_proposal_invalid_stop(self):
        adapter = JevAdapter()
        # Invalid: Buy with stop loss higher than entry price
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Momentum trade.",
            entry_price=90000.0,
            stop_loss=95000.0,
            position_sizing="5% of portfolio",
            symbol="BTC-USD",
        )
        score_res = adapter.score_trader_proposal(proposal)
        assert score_res["stop_valid"] is False
        assert score_res["approved"] is False

    def test_score_risk_consensus(self):
        adapter = JevAdapter()
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Trend following.",
            entry_price=3000.0,
            stop_loss=2850.0,
            position_sizing="3% of portfolio",
            symbol="ETH-USD",
        )
        risk_debate_state = {
            "current_aggressive_response": "Aggressive: Upside potential warrants 5% allocation.",
            "current_conservative_response": "Conservative: Cautious on volatility, cap sizing at 3% with strict stop.",
            "current_neutral_response": "Neutral: Agree with 3% position and 2850 stop.",
            "history": "Debate reached consensus on 3% sizing.",
        }
        res = adapter.score_risk_consensus(proposal, risk_debate_state)
        assert "consensus_achieved" in res
        assert "dominant_posture" in res
        assert "downside_protection" in res


@pytest.mark.unit
class TestAntigravityAndInterfaceContracts:
    """Verifies Antigravity SDK client, thinking levels, and interface contracts."""

    def test_interface_contract_trader_proposal(self):
        proposal = TraderProposal(
            action="Buy",
            reasoning="Technical breakout above resistance.",
            entry_price=150.0,
            stop_loss=142.0,
            position_sizing="4% of portfolio",
            symbol="SOL-USD",
        )
        assert proposal.action == TraderAction.BUY
        assert proposal.entry_price == 150.0
        assert proposal.stop_loss == 142.0
        assert proposal.symbol == "SOL-USD"
        dump = proposal.model_dump()
        assert dump["symbol"] == "SOL-USD"
        assert dump["action"] == "Buy"

    def test_interface_contract_portfolio_decision(self):
        decision = PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="Enter long position with 5% allocation and 3-month horizon.",
            investment_thesis="Growth catalyst supported by positive macro and technical structure.",
            price_target=110000.0,
            time_horizon="3-6 months",
        )
        assert decision.rating == PortfolioRating.BUY
        assert decision.price_target == 110000.0
        assert decision.time_horizon == "3-6 months"

    def test_antigravity_llm_factory(self):
        client = create_llm_client(
            provider="antigravity",
            model="gemini-3.8-flash",
            thinking_level="high",
        )
        assert isinstance(client, AntigravityClient)
        assert client.model == "gemini-3.8-flash"
        assert client.kwargs.get("thinking_level") == "high"

    def test_antigravity_trading_hierarchy(self):
        hierarchy = create_antigravity_trading_hierarchy({})
        assert "root" in hierarchy
        assert hierarchy["root"]["name"] == "portfolio_manager"
        assert hierarchy["root"]["capabilities"]["enable_subagents"] is True
        assert hierarchy["root"]["capabilities"]["max_subagent_depth"] == 3
        assert "analyst_team" in hierarchy
        assert len(hierarchy["analyst_team"]["allowed_subagents"]) == 4
        assert "research_team" in hierarchy
        assert len(hierarchy["research_team"]["allowed_subagents"]) == 3
        assert "risk_team" in hierarchy
        assert len(hierarchy["risk_team"]["allowed_subagents"]) == 3
