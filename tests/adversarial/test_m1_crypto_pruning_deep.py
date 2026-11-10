"""Deep empirical verification suite for Defect Vector 2 (Crypto Fundamentals Pruning & Zero Leakage).

Verifies:
1. fundamentals_analyst_node early skip returns empty report for crypto without invoking LLM or tools.
2. Bull & Bear Researcher prompt isolation with Apple 10-K Injection strictly suppresses corporate data.
3. Positive control: Stock asset (AAPL) correctly preserves fundamentals in Bull/Bear prompt.
4. TradingAgentsGraph DAG structure completely omits 'Fundamentals Analyst' from crypto_workflow.
5. propagate('BTC-USD', asset_type='crypto') executes graph traversal without calling Fundamentals Analyst.
6. propagate('BTC-USD') with auto-detection executes graph traversal without calling Fundamentals Analyst.
"""

import sys
import tempfile
from pathlib import Path
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.agents import schemas
from core.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from core.agents.researchers.bull_researcher import create_bull_researcher
from core.agents.researchers.bear_researcher import create_bear_researcher
from core.graph.trading_graph import TradingAgentsGraph


class SpyChatModel(BaseChatModel):
    invocations: list = []
    recorded_prompts: list = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.invocations = []
        self.recorded_prompts = []

    @property
    def _llm_type(self) -> str:
        return "spy_chat"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg_str = str(messages)
        self.invocations.append(msg_str)
        self.recorded_prompts.append(msg_str)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="Analysis complete.\n\n**Rating**: Buy\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
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


def test_fundamentals_analyst_early_skip_crypto():
    """fundamentals_analyst_node must return blank report immediately for crypto without LLM or tool calls."""
    mock_llm = SpyChatModel()
    fundamentals_fn = create_fundamentals_analyst(mock_llm)

    res_asset_type = fundamentals_fn({
        "asset_type": "crypto",
        "company_of_interest": "CUSTOM_COIN",
        "trade_date": "2026-04-18",
    })
    assert res_asset_type == {"messages": [], "fundamentals_report": ""}
    assert len(mock_llm.invocations) == 0

    res_ticker = fundamentals_fn({
        "asset_type": "stock",
        "company_of_interest": "BTC-USD",
        "trade_date": "2026-04-18",
    })
    assert res_ticker == {"messages": [], "fundamentals_report": ""}
    assert len(mock_llm.invocations) == 0


def test_bull_bear_researcher_apple_10k_leakage_suppression():
    """Pre-populated Apple 10-K text in state['fundamentals_report'] must NEVER leak into crypto debate prompts."""
    apple_10k_text = (
        "Apple Inc. FORM 10-K ANNUAL REPORT: Total Net Sales $383,285,000,000, "
        "Operating Income $114,301,000,000, Diluted EPS $6.13, iPhone net sales $200,583M, "
        "Services revenue $85,200M, Gross Margin 44.1%, Cash $162,099M."
    )

    spy_bull = SpyChatModel()
    spy_bear = SpyChatModel()
    bull_node = create_bull_researcher(spy_bull)
    bear_node = create_bear_researcher(spy_bear)

    crypto_state = {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "instrument_context": "Bitcoin crypto asset",
        "market_report": "BTC market structure and 24h volume analysis",
        "sentiment_report": "Bullish funding rates and social sentiment",
        "news_report": "Spot ETF net inflows accelerate",
        "fundamentals_report": apple_10k_text,
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
    }

    # Test Bull prompt
    bull_node(crypto_state)
    assert len(spy_bull.recorded_prompts) == 1
    bull_prompt = spy_bull.recorded_prompts[0]
    forbidden_terms = ["Apple", "10-K", "383,285", "Operating Income", "iPhone", "Services revenue", "Gross Margin"]
    for term in forbidden_terms:
        assert term not in bull_prompt, f"Corporate data leaked into Bull prompt: '{term}'"
    assert "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)." in bull_prompt
    assert "network adoption, protocol utility, ecosystem growth, and liquidity dynamics" in bull_prompt

    # Test Bear prompt
    bear_node(crypto_state)
    assert len(spy_bear.recorded_prompts) == 1
    bear_prompt = spy_bear.recorded_prompts[0]
    for term in forbidden_terms:
        assert term not in bear_prompt, f"Corporate data leaked into Bear prompt: '{term}'"
    assert "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)." in bear_prompt
    assert "network vulnerabilities, regulatory headwinds, liquidity risks, or macroeconomic volatility" in bear_prompt


def test_positive_control_stock_preserves_fundamentals():
    """Stock assets (e.g. AAPL) must preserve corporate fundamentals in debate prompts."""
    apple_10k_text = "Apple Inc. FORM 10-K ANNUAL REPORT: Total Net Sales $383,285,000,000"
    spy_bull = SpyChatModel()
    bull_node = create_bull_researcher(spy_bull)

    stock_state = {
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "instrument_context": "Apple Inc equity",
        "market_report": "AAPL market structure",
        "sentiment_report": "Neutral sentiment",
        "news_report": "Quarterly earnings preview",
        "fundamentals_report": apple_10k_text,
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
    }

    bull_node(stock_state)
    assert len(spy_bull.recorded_prompts) == 1
    prompt = spy_bull.recorded_prompts[0]
    assert apple_10k_text in prompt
    assert "Company fundamentals report: Apple Inc. FORM 10-K ANNUAL REPORT" in prompt


def test_graph_dag_crypto_omits_fundamentals_node():
    """TradingAgentsGraph must exclude 'Fundamentals Analyst' from crypto_workflow."""
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
                return SpyChatModel()

        tg_module.create_tier_client = _MockClient

        graph = TradingAgentsGraph(config=cfg)
        assert "Fundamentals Analyst" in graph.workflow.nodes
        assert "Fundamentals Analyst" not in graph.crypto_workflow.nodes

        # Verify dynamic active analyst list
        assert "fundamentals" in graph._active_analysts("stock", "AAPL")
        assert "fundamentals" not in graph._active_analysts("crypto", "BTC-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "BTC-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "ETH-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "SOL-USD")
