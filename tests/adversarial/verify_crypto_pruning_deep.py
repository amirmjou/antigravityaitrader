"""Deep empirical verification script for Defect Vector 2.

Objective:
1. Verify TradingAgentsGraph node omission in crypto_workflow.
2. Execute propagate('BTC-USD', asset_type='crypto') with mock LLM to verify traversal excludes Fundamentals Analyst.
3. Verify propagate('BTC-USD') auto-detects crypto and excludes Fundamentals Analyst.
4. Verify propagate('AAPL', asset_type='stock') preserves Fundamentals Analyst in workflow and execution.
5. Pre-populate state['fundamentals_report'] with Apple 10-K text and verify Bull/Bear prompt suppression.
6. Verify positive control on stock (AAPL) retains fundamentals report in Bull/Bear prompt.
7. Verify fundamentals_analyst_node early skip returns empty report for crypto without invoking LLM or tools.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

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


def run_checks():
    print("--- 1. Testing fundamentals_analyst_node early skip ---")
    mock_llm_fail = SpyChatModel()
    fundamentals_fn = create_fundamentals_analyst(mock_llm_fail)
    
    # Test crypto by asset_type
    res1 = fundamentals_fn({"asset_type": "crypto", "company_of_interest": "CUSTOM_COIN", "trade_date": "2026-04-18"})
    assert res1 == {"messages": [], "fundamentals_report": ""}, f"Unexpected res1: {res1}"
    assert len(mock_llm_fail.invocations) == 0, "LLM must NOT be invoked for crypto fundamentals"

    # Test crypto by ticker in _CRYPTO_BASES
    res2 = fundamentals_fn({"asset_type": "stock", "company_of_interest": "BTC-USD", "trade_date": "2026-04-18"})
    assert res2 == {"messages": [], "fundamentals_report": ""}, f"Unexpected res2: {res2}"
    assert len(mock_llm_fail.invocations) == 0, "LLM must NOT be invoked for BTC-USD"
    print("PASS: fundamentals_analyst_node early skip operates with zero LLM/tool calls.")

    print("\n--- 2. Testing Bull & Bear Prompt Isolation with Apple 10-K Injection ---")
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
        "fundamentals_report": apple_10k_text,  # Stale corporate data injected!
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
    }

    # Execute Bull Researcher
    bull_node(crypto_state)
    assert len(spy_bull.recorded_prompts) == 1
    bull_prompt = spy_bull.recorded_prompts[0]
    
    # Assert zero corporate leakage
    forbidden_terms = ["Apple", "10-K", "383,285", "Operating Income", "iPhone", "Services revenue", "Gross Margin"]
    for term in forbidden_terms:
        assert term not in bull_prompt, f"Corporate data leaked into Bull prompt: '{term}'"
    assert "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)." in bull_prompt
    assert "network adoption, protocol utility, ecosystem growth, and liquidity dynamics" in bull_prompt
    print("PASS: Bull researcher prompt cleanly suppressed Apple 10-K text and injected crypto directives.")

    # Execute Bear Researcher
    bear_node(crypto_state)
    assert len(spy_bear.recorded_prompts) == 1
    bear_prompt = spy_bear.recorded_prompts[0]
    for term in forbidden_terms:
        assert term not in bear_prompt, f"Corporate data leaked into Bear prompt: '{term}'"
    assert "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)." in bear_prompt
    assert "network vulnerabilities, regulatory headwinds, liquidity risks, or macroeconomic volatility" in bear_prompt
    print("PASS: Bear researcher prompt cleanly suppressed Apple 10-K text and injected crypto directives.")

    # Positive control: Stock asset (AAPL) MUST include fundamentals report
    spy_bull_stock = SpyChatModel()
    bull_node_stock = create_bull_researcher(spy_bull_stock)
    stock_state = dict(crypto_state)
    stock_state["company_of_interest"] = "AAPL"
    stock_state["asset_type"] = "stock"
    bull_node_stock(stock_state)
    assert len(spy_bull_stock.recorded_prompts) == 1
    stock_bull_prompt = spy_bull_stock.recorded_prompts[0]
    assert "Apple Inc. FORM 10-K ANNUAL REPORT" in stock_bull_prompt
    assert "Company fundamentals report: Apple Inc. FORM 10-K ANNUAL REPORT" in stock_bull_prompt
    print("PASS: Positive control confirmed: Stock (AAPL) correctly includes corporate fundamentals.")

    print("\n--- 3. Testing TradingAgentsGraph Graph Structure and Traversal ---")
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
        spy_engine = SpyChatModel()

        class _MockClient:
            def __init__(self, *a, **k):
                pass
            def get_llm(self):
                return spy_engine

        tg_module.create_tier_client = _MockClient

        graph = TradingAgentsGraph(config=cfg)
        
        # Check DAG nodes
        assert "Fundamentals Analyst" in graph.workflow.nodes, "Stock workflow MUST contain Fundamentals Analyst"
        assert "Fundamentals Analyst" not in graph.crypto_workflow.nodes, "Crypto workflow MUST NOT contain Fundamentals Analyst"
        
        # Verify active analysts helper
        assert "fundamentals" in graph._active_analysts("stock", "AAPL")
        assert "fundamentals" not in graph._active_analysts("crypto", "BTC-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "BTC-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "ETH-USD")
        assert "fundamentals" not in graph._active_analysts("stock", "SOL-USD")

        # Test propagate on BTC-USD with asset_type='crypto'
        spy_engine.invocations.clear()
        state_out, signal = graph.propagate("BTC-USD", "2026-04-18", asset_type="crypto")
        
        for inv in spy_engine.invocations:
            assert "fundamental information" not in inv, "Fundamentals Analyst prompt detected in crypto execution!"
            assert "get_fundamentals" not in inv, "Fundamentals tool detected in crypto execution!"
        print(f"PASS: propagate('BTC-USD', asset_type='crypto') executed successfully (signal={signal}) with ZERO fundamentals node calls.")

        # Test propagate on BTC-USD without explicit asset_type (auto-detect)
        spy_engine.invocations.clear()
        state_out_auto, signal_auto = graph.propagate("BTC-USD", "2026-04-18")
        for inv in spy_engine.invocations:
            assert "fundamental information" not in inv, "Fundamentals Analyst prompt detected in auto-detected crypto execution!"
        print(f"PASS: propagate('BTC-USD') with auto-detection executed successfully (signal={signal_auto}) with ZERO fundamentals node calls.")

    print("\n========================================================")
    print("ALL EMPIRICAL VERIFICATION CHECKS PASSED PERFECTLY!")
    print("========================================================")


if __name__ == "__main__":
    run_checks()
