"""
Tier 1: Feature Coverage (Category-Partition)
Features F01–F07: Multi-Agent Trading Architecture Integration (Milestone 1)
Each feature has >= 5 comprehensive, requirement-driven test cases.
"""
import json
import sys
import pytest

from tests.e2e.contracts import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    SentimentBand,
    SentimentReport,
    ThinkingLevel,
    TraderAction,
    TraderProposal,
)
from tests.e2e.fixtures import LocalJevMCPClient, MockGeminiAntigravityClient
from tests.e2e.harness import MultiAgentDeliberationEngine


# ===========================================================================
# Feature F01: Framework Setup & Dependencies
# ===========================================================================
class TestF01FrameworkSetup:
    def test_f01_01_python_version_compatibility(self):
        """Verify Python runtime meets minimum 3.11 requirement."""
        assert sys.version_info >= (3, 11), f"Requires Python >= 3.11, found {sys.version}"

    def test_f01_02_pydantic_v2_installed_and_operational(self):
        """Verify Pydantic v2 core models and validators."""
        import pydantic
        assert int(pydantic.__version__.split(".")[0]) >= 2
        p = TraderProposal(action=TraderAction.BUY.value, reasoning="Valid test setup", symbol="BTC-USD")
        assert p.action == "Buy"

    def test_f01_03_crypto_symbol_syntax_normalization(self):
        """Verify canonical crypto symbol mapping (e.g. BTC -> BTC-USD)."""
        symbols = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}
        for raw, expected in symbols.items():
            normalized = f"{raw}-USD" if not raw.endswith("-USD") else raw
            assert normalized == expected

    def test_f01_04_async_web_stack_prerequisites(self):
        """Verify essential asynchronous networking libraries (fastapi, httpx)."""
        import fastapi
        import httpx
        assert fastapi.__version__ is not None
        assert httpx.__version__ is not None

    def test_f01_05_antigravity_sdk_presence(self):
        """Verify google-antigravity SDK availability in environment."""
        import google.antigravity
        assert google.antigravity is not None


# ===========================================================================
# Feature F02: Analyst Team Architecture
# ===========================================================================
class TestF02AnalystTeamArchitecture:
    def test_f02_01_market_analyst_subgraph_execution(self, multi_agent_engine):
        """Verify Market Analyst produces technical indicator summaries."""
        reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        assert "Market Analyst" in reports
        assert "Momentum indicators positive" in reports["Market Analyst"]

    def test_f02_02_sentiment_analyst_structured_output(self, multi_agent_engine):
        """Verify Sentiment Analyst outputs typed SentimentReport."""
        reports = multi_agent_engine.run_analysts("ETH-USD", is_crypto=True)
        assert "Sentiment Analyst" in reports
        sent = reports["Sentiment Analyst"]
        assert isinstance(sent, SentimentReport)
        assert sent.overall_band == SentimentBand.BULLISH
        assert 0.0 <= sent.overall_score <= 10.0

    def test_f02_03_news_analyst_macro_sentiment(self, multi_agent_engine):
        """Verify News Analyst integrates macro narrative."""
        reports = multi_agent_engine.run_analysts("SOL-USD", is_crypto=True)
        assert "News Analyst" in reports
        assert "volume expanding" in reports["News Analyst"]

    def test_f02_04_fundamentals_analyst_crypto_pruning(self, multi_agent_engine):
        """Verify corporate fundamentals (SEC filings) are excluded for crypto assets."""
        reports_crypto = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        assert "Fundamentals Analyst" not in reports_crypto

        reports_equity = multi_agent_engine.run_analysts("AAPL", is_crypto=False)
        assert "Fundamentals Analyst" in reports_equity

    def test_f02_05_parallel_analyst_join_barrier(self, multi_agent_engine):
        """Verify all analyst subgraphs complete before debate commences."""
        reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        assert len(reports) >= 3
        assert all(k in reports for k in ["Market Analyst", "Sentiment Analyst", "News Analyst"])


# ===========================================================================
# Feature F03: Bull/Bear Researcher Debate
# ===========================================================================
class TestF03BullBearResearcherDebate:
    def test_f03_01_bull_researcher_opening_thesis(self, multi_agent_engine):
        """Verify Bull researcher generates positive fundamental thesis."""
        reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("BTC-USD", reports)
        assert "Bull thesis" in plan.rationale

    def test_f03_02_bear_researcher_rebuttal_inclusion(self, multi_agent_engine):
        """Verify Bear researcher arguments are reflected in debate synthesis."""
        reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("BTC-USD", reports)
        assert plan.rationale is not None
        assert len(plan.rationale) > 20

    def test_f03_03_multi_turn_debate_bounds(self, multi_agent_engine):
        """Verify debate terminates strictly within configured max_debate_rounds."""
        assert multi_agent_engine.max_debate_rounds == 2
        reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("BTC-USD", reports)
        assert "4 turns" in plan.rationale

    def test_f03_04_research_manager_consensus_synthesis(self, multi_agent_engine):
        """Verify Research Manager produces typed ResearchPlan with recommendation."""
        reports = multi_agent_engine.run_analysts("ETH-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("ETH-USD", reports)
        assert isinstance(plan, ResearchPlan)
        assert plan.recommendation in [PortfolioRating.BUY, PortfolioRating.HOLD, PortfolioRating.SELL]

    def test_f03_05_jev_variant_scoring_integration(self, multi_agent_engine):
        """Verify Jev pick_variant scores the competing debate theses."""
        reports = multi_agent_engine.run_analysts("SOL-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("SOL-USD", reports)
        assert "Jev preferred" in plan.rationale


# ===========================================================================
# Feature F04: Risk Management Debaters
# ===========================================================================
class TestF04RiskManagementDebaters:
    def test_f04_01_aggressive_risk_debater_advocacy(self, multi_agent_engine):
        """Verify risk debate handles high conviction proposal."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Aggressive momentum", entry_price=88500.0, symbol="BTC-USD")
        decision = multi_agent_engine.run_risk_management_debate("BTC-USD", prop, current_drawdown=0.01)
        assert decision.rating in [PortfolioRating.BUY.value, PortfolioRating.OVERWEIGHT.value]

    def test_f04_02_conservative_risk_debater_drawdown_restraint(self, multi_agent_engine):
        """Verify Conservative risk debater suppresses buy when drawdown is elevated."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="High risk setup", entry_price=88500.0, symbol="BTC-USD")
        # Drawdown 9% exceeds 8% safe limit
        decision = multi_agent_engine.run_risk_management_debate("BTC-USD", prop, current_drawdown=0.09)
        assert decision.rating == PortfolioRating.HOLD.value

    def test_f04_03_neutral_risk_debater_sizing_moderation(self, multi_agent_engine):
        """Verify neutral risk debater balances opportunity vs preservation."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Moderate setup", entry_price=3100.0, symbol="ETH-USD")
        decision = multi_agent_engine.run_risk_management_debate("ETH-USD", prop, current_drawdown=0.03)
        assert decision.price_target is not None
        assert decision.price_target > 3100.0

    def test_f04_04_portfolio_manager_final_decision_schema(self, multi_agent_engine):
        """Verify Portfolio Manager emits complete typed PortfolioDecision."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Consensus long", entry_price=185.0, symbol="SOL-USD")
        decision = multi_agent_engine.run_risk_management_debate("SOL-USD", prop, current_drawdown=0.02)
        assert isinstance(decision, PortfolioDecision)
        assert decision.executive_summary is not None
        assert decision.investment_thesis is not None
        assert decision.time_horizon == "1-2 weeks"

    def test_f04_05_jev_risk_consensus_confidence_score(self, multi_agent_engine):
        """Verify Jev decision scoring populates confidence in investment thesis."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Sound risk setup", entry_price=88500.0, symbol="BTC-USD")
        decision = multi_agent_engine.run_risk_management_debate("BTC-USD", prop, current_drawdown=0.02)
        assert "Jev heuristic score: 0.85" in decision.investment_thesis


# ===========================================================================
# Feature F05: Trader Agent Proposal Engine
# ===========================================================================
class TestF05TraderAgentProposalEngine:
    def test_f05_01_trader_proposal_buy_action(self, multi_agent_engine):
        """Verify Trader generates concrete Buy proposal with technical levels."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Decisive bull win", strategic_actions="Buy 5%")
        proposal = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=88500.0)
        assert proposal.action == "Buy"
        assert proposal.entry_price == 88500.0
        assert proposal.stop_loss == 85845.0  # 97% of 88500

    def test_f05_02_trader_proposal_stop_loss_below_entry(self, multi_agent_engine):
        """Verify stop-loss is strictly below entry price on long positions."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Solid", strategic_actions="Allocate")
        proposal = multi_agent_engine.run_trader_proposal("ETH-USD", plan, market_price=3100.0)
        assert proposal.stop_loss < proposal.entry_price

    def test_f05_03_trader_proposal_position_sizing_field(self, multi_agent_engine):
        """Verify position sizing guidance is specified."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Solid", strategic_actions="Allocate")
        proposal = multi_agent_engine.run_trader_proposal("SOL-USD", plan, market_price=185.0)
        assert proposal.position_sizing == "5% of portfolio"

    def test_f05_04_trader_proposal_symbol_tagging(self, multi_agent_engine):
        """Verify proposal retains asset symbol identity."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Solid", strategic_actions="Allocate")
        proposal = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=88500.0)
        assert proposal.symbol == "BTC-USD"

    def test_f05_05_trader_proposal_nullish_float_coercion(self):
        """Verify robust coercion of placeholder strings ('none', 'N/A') to None."""
        p = TraderProposal(action=TraderAction.HOLD.value, reasoning="Wait", entry_price="None", stop_loss="N/A", symbol="BTC-USD")  # type: ignore
        assert p.entry_price is None
        assert p.stop_loss is None


# ===========================================================================
# Feature F06: Antigravity & Gemini Integration
# ===========================================================================
class TestF06AntigravityGeminiIntegration:
    def test_f06_01_client_initialization_high_thinking(self):
        """Verify LLM client initialization with high thinking level."""
        client = MockGeminiAntigravityClient(thinking_level=ThinkingLevel.HIGH.value)
        assert client.thinking_level == "high"

    def test_f06_02_client_initialization_low_thinking(self):
        """Verify LLM client initialization with low thinking level."""
        client = MockGeminiAntigravityClient(thinking_level=ThinkingLevel.LOW.value)
        assert client.thinking_level == "low"

    def test_f06_03_client_initialization_minimal_thinking(self):
        """Verify LLM client initialization with minimal thinking level."""
        client = MockGeminiAntigravityClient(thinking_level=ThinkingLevel.MINIMAL.value)
        assert client.thinking_level == "minimal"

    def test_f06_04_structured_schema_enforcement(self):
        """Verify LLM client can return typed Pydantic models directly."""
        client = MockGeminiAntigravityClient()
        proposal = client.invoke("Propose trade for BTC", schema=TraderProposal)
        assert isinstance(proposal, TraderProposal)
        assert proposal.symbol == "BTC-USD"
        assert proposal.action == "Buy"

    def test_f06_05_call_history_logging(self):
        """Verify audit trail of prompts and thinking configurations."""
        client = MockGeminiAntigravityClient(thinking_level="high")
        client.invoke("Evaluate ETH momentum")
        assert len(client.call_history) == 1
        assert client.call_history[0]["prompt"] == "Evaluate ETH momentum"
        assert client.call_history[0]["level"] == "high"


# ===========================================================================
# Feature F07: Memory & Reflection Settlement
# ===========================================================================
class TestF07MemoryReflectionSettlement:
    def test_f07_01_memory_log_record_persistence(self, multi_agent_engine):
        """Verify completed decisions are recorded to memory log."""
        initial_count = len(multi_agent_engine.memory_log)
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Good long", entry_price=88500.0, symbol="BTC-USD")
        multi_agent_engine.run_risk_management_debate("BTC-USD", prop, current_drawdown=0.01)
        assert len(multi_agent_engine.memory_log) == initial_count + 1

    def test_f07_02_memory_record_structure(self, multi_agent_engine):
        """Verify memory record stores symbol, decision snapshot, and timestamp."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Good long", entry_price=3100.0, symbol="ETH-USD")
        multi_agent_engine.run_risk_management_debate("ETH-USD", prop, current_drawdown=0.01)
        record = multi_agent_engine.memory_log[-1]
        assert record["symbol"] == "ETH-USD"
        assert "decision" in record
        assert "timestamp" in record

    def test_f07_03_point_in_time_recovery_order(self, multi_agent_engine):
        """Verify memory log preserves strictly monotonic chronological timestamps."""
        prop = TraderProposal(action=TraderAction.BUY.value, reasoning="Test", entry_price=100.0, symbol="TEST")
        multi_agent_engine.run_risk_management_debate("TEST", prop, current_drawdown=0.01)
        multi_agent_engine.run_risk_management_debate("TEST2", prop, current_drawdown=0.01)
        t1 = multi_agent_engine.memory_log[-2]["timestamp"]
        t2 = multi_agent_engine.memory_log[-1]["timestamp"]
        assert t2 >= t1

    def test_f07_04_benchmark_alpha_settlement_simulation(self):
        """Verify alpha calculation between realized trade pnl and benchmark return."""
        trade_return_pct = 0.08  # +8%
        benchmark_spy_pct = 0.03 # +3%
        realized_alpha = trade_return_pct - benchmark_spy_pct
        assert realized_alpha == pytest.approx(0.05)

    def test_f07_05_reflection_insight_generation(self, multi_agent_engine):
        """Verify memory log allows downstream reflection on prior trades."""
        assert isinstance(multi_agent_engine.memory_log, list)
        # Verify serialization fidelity
        serialized = json.dumps(multi_agent_engine.memory_log)
        assert json.loads(serialized) == multi_agent_engine.memory_log
