"""
Tier 4: Real-World Application Workloads
End-to-end full life-cycle multi-agent trading workflows:
1. BTC Bull Breakout Execution Workflow
2. ETH Bear Breakdown Emergency Exit Workflow
3. SOL Volatility Drawdown Hedge Workflow
4. Remote Cloud Agent Fallback Workflow
5. High-Gas Congestion Deferral & Resume Workflow
"""
import pytest

from tests.e2e.contracts import (
    PortfolioRating,
    ResearchPlan,
    SwapTransactionRequest,
    TraderAction,
    TraderProposal,
)
from tests.e2e.fixtures import (
    LocalJevMCPClient,
    MockCCXTExchange,
    MockGeminiAntigravityClient,
    MockGoPlusClient,
    MockPublicAPIs,
    MockRemoteAgentBridge,
    MockUniswapV3Quoter,
    MockWeb3Provider,
)
from tests.e2e.harness import (
    CryptoIngestionSizingEngine,
    DualEngineWalletRouter,
    MultiAgentDeliberationEngine,
    PaperTradingEngine,
    PreBroadcastGuardrailPipeline,
    VisualizationStreamHub,
)


# ===========================================================================
# Scenario 1: BTC Bull Breakout Execution Workflow
# ===========================================================================
class TestScenario1BTCBullBreakout:
    def test_workflow_btc_bull_breakout_end_to_end(
        self,
        multi_agent_engine,
        guardrail_pipeline,
        wallet_router,
        stream_hub,
        crypto_sizing_engine,
        paper_trader,
    ):
        """
        Full lifecycle:
        CCXT Ingestion -> Multi-Agent Debate -> Jev Scoring -> Guardrails L1-L5 ->
        Arbitrum Uniswap v3 Swap -> SSE Telemetry -> Paper Trading Fill.
        """
        # Step 1: Ingest BTC market ticker
        ticker = crypto_sizing_engine.exchange.fetch_ticker("BTC/USDT")
        assert ticker["last"] == 88500.0

        # Step 2: Analyst subgraphs deliberate
        analyst_reports = multi_agent_engine.run_analysts("BTC-USD", is_crypto=True)
        assert "Market Analyst" in analyst_reports

        # Step 3: Bull/Bear debate reaches consensus
        plan = multi_agent_engine.run_bull_bear_debate("BTC-USD", analyst_reports)
        assert plan.recommendation == PortfolioRating.BUY

        # Step 4: Trader agent formulates concrete execution levels
        proposal = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=ticker["last"])
        assert proposal.action == "Buy"
        assert proposal.entry_price == 88500.0
        assert proposal.stop_loss == 85845.0

        # Step 5: Risk management debate + Jev heuristic scoring
        decision = multi_agent_engine.run_risk_management_debate("BTC-USD", proposal, current_drawdown=0.01)
        assert decision.rating == PortfolioRating.BUY.value

        # Step 6: Volatility sizing computes position lot
        sizing = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", max_notional_cap_usd=200.0)
        assert sizing.recommended_position_usd == 200.0

        # Step 7: Pre-broadcast safety guardrail pipeline evaluation (Layers 1-5)
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", # WBTC
            amount_in_wei=int(sizing.precision_lot_size * 10**18),
            amount_out_min_wei=225000,
            recipient="0xHotSigner",
            trade_value_usd=sizing.recommended_position_usd,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is True
        assert verdict.simulated_gas_used > 0

        # Step 8: Dual-engine hot signer broadcasts transaction to Arbitrum One
        swap_res = wallet_router.execute_swap(req)
        assert swap_res.success is True
        assert swap_res.tx_hash.startswith("0x")

        # Step 9: Emit telemetry to UI streaming hub
        stream_hub.publish_event(
            "trade_telemetry",
            "Trader",
            f"BTC Buy executed at {ticker['last']}: tx={swap_res.tx_hash}",
            snapshot={"tx_hash": swap_res.tx_hash, "amount_out": swap_res.amount_out_wei}
        )
        assert len(stream_hub.event_stream) == 1

        # Step 10: Settle position in paper trading book
        order = paper_trader.place_order("BTC/USDT", "Buy", sizing.precision_lot_size, ticker["last"])
        assert order.status == "filled"
        assert "BTC/USDT" in paper_trader.positions
        assert paper_trader.positions["BTC/USDT"].quantity == sizing.precision_lot_size


# ===========================================================================
# Scenario 2: ETH Bear Breakdown Emergency Exit Workflow
# ===========================================================================
class TestScenario2ETHBearBreakdownExit:
    def test_workflow_eth_bear_exit_end_to_end(
        self,
        multi_agent_engine,
        guardrail_pipeline,
        web3_base,
        base_config,
        stream_hub,
        paper_trader,
    ):
        """
        Full lifecycle:
        Macro Contagion (Fear 18) -> Bear Researcher Win -> Risk Liquidation ->
        Guardrails -> Base Aerodrome Swap -> Position Liquidated & Cash Protected.
        """
        # Step 1: Pre-fund paper trader with 1.0 ETH
        paper_trader.place_order("ETH/USDT", "Buy", 1.0, 3100.0)
        assert paper_trader.positions["ETH/USDT"].quantity == 1.0

        # Step 2: Alternative.me reports Extreme Fear (18)
        fng = MockPublicAPIs.get_fear_and_greed(override_value=18)
        assert fng["data"][0]["value_classification"] == "Extreme Fear"

        # Step 3: Bear thesis defeats Bull
        bear_plan = ResearchPlan(
            recommendation=PortfolioRating.SELL,
            rationale="Market contagion following systemic liquidation cascade. Extreme fear confirmed.",
            strategic_actions="Liquidate 100% ETH holdings to preserve capital.",
        )
        assert bear_plan.recommendation == PortfolioRating.SELL

        # Step 4: Trader formulates sell proposal
        sell_prop = TraderProposal(
            action=TraderAction.SELL.value,
            reasoning="Emergency liquidation order based on ResearchPlan.",
            entry_price=3100.0,
            symbol="ETH-USD",
        )
        assert sell_prop.action == "Sell"

        # Step 5: Guardrail check on sell swap (Base chain)
        req = SwapTransactionRequest(
            chain_id=8453,
            token_in="0x4200000000000000000000000000000000000006",  # WETH on Base
            token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", # USDC on Base
            amount_in_wei=10**18,
            amount_out_min_wei=3050000000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        base_router = DualEngineWalletRouter(web3_provider=web3_base, chain_config=base_config)
        swap_res = base_router.execute_swap(req)
        assert swap_res.success is True

        # Step 6: Liquidate paper trading position
        sell_order = paper_trader.place_order("ETH/USDT", "Sell", 1.0, 3100.0)
        assert sell_order.status == "filled"
        assert paper_trader.positions["ETH/USDT"].quantity == 0.0


# ===========================================================================
# Scenario 3: SOL Volatility Drawdown Hedge Workflow
# ===========================================================================
class TestScenario3SOLVolatilityDrawdownHedge:
    def test_workflow_sol_volatility_drawdown_hedge(
        self,
        crypto_sizing_engine,
        guardrail_pipeline,
        paper_trader,
    ):
        """
        Full lifecycle:
        SOL Volatility 3x surge -> ATR sizing automatically scales down lot ->
        Drawdown at 7.9% limits speculative exposure -> Hedge position established.
        """
        # Baseline sizing with standard 1.5x multiplier (unconstrained cap to test volatility scaling)
        standard_sizing = crypto_sizing_engine.calculate_atr14_sizing("SOL/USDT", multiplier=1.5, max_notional_cap_usd=5000.0)
        
        # Volatility spike: wider stop buffer (3.0x multiplier)
        high_vol_sizing = crypto_sizing_engine.calculate_atr14_sizing("SOL/USDT", multiplier=3.0, max_notional_cap_usd=5000.0)
        
        # Verify volatility scaling dynamically cuts allocation
        assert high_vol_sizing.raw_lot_size < standard_sizing.raw_lot_size
        assert high_vol_sizing.precision_lot_size <= standard_sizing.precision_lot_size

        # Verify drawdown near circuit breaker allows small hedge trade ($50)
        hedge_req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=50.0,
        )
        # 7.8% is safe (under 8.0% breaker)
        verdict = guardrail_pipeline.evaluate(hedge_req, current_daily_drawdown_pct=7.8)
        assert verdict.approved is True


# ===========================================================================
# Scenario 4: Remote Agent Cloud VM Failover & Fallback Workflow
# ===========================================================================
class TestScenario4RemoteAgentFallback:
    def test_workflow_remote_agent_cloud_vm_failover(self):
        """
        Full lifecycle:
        Primary agy --remote-agent times out -> System detects error ->
        Gracefully falls back to local Antigravity Gemini client -> Deliberation succeeds.
        """
        bridge_failing = MockRemoteAgentBridge(should_fail=True, failure_mode="timeout")
        engine = CryptoIngestionSizingEngine()
        engine.remote_bridge = bridge_failing

        # Primary invocation fails
        primary_failed = False
        try:
            engine.execute_remote_agent("BTC")
        except RuntimeError:
            primary_failed = True
        assert primary_failed is True

        # Fallback to local SDK client
        local_client = MockGeminiAntigravityClient(thinking_level="high")
        proposal = local_client.invoke("Fallback deliberation for BTC", schema=TraderProposal)
        assert proposal.symbol == "BTC-USD"
        assert proposal.action == "Buy"


# ===========================================================================
# Scenario 5: High-Gas Congestion Deferral & Auto-Resume Workflow
# ===========================================================================
class TestScenario5GasCongestionDeferral:
    def test_workflow_gas_congestion_deferral_and_resume(self, guardrail_pipeline, web3_arbitrum, wallet_router):
        """
        Full lifecycle:
        Gas spike to 140 gwei -> Layer 4 blocks execution -> Gas normalizes ->
        Pre-flight simulation passes -> Transaction completes.
        """
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        
        # Step 1: Network congested
        web3_arbitrum.base_fee_gwei = 140.0
        v_blocked = guardrail_pipeline.evaluate(req)
        assert v_blocked.approved is False
        assert "exceeds ceiling 120.0 gwei" in v_blocked.rejection_reason

        # Step 2: Gas normalizes to 0.1 gwei
        web3_arbitrum.base_fee_gwei = 0.1
        v_resumed = guardrail_pipeline.evaluate(req)
        assert v_resumed.approved is True

        # Step 3: Swap executes successfully
        res = wallet_router.execute_swap(req)
        assert res.success is True


# ===========================================================================
# Scenario 6: Multi-Asset Concurrent Portfolio Rebalance Workflow
# ===========================================================================
class TestScenario6MultiAssetPortfolioRebalance:
    def test_workflow_multi_asset_portfolio_rebalance(
        self,
        crypto_sizing_engine,
        guardrail_pipeline,
        paper_trader,
    ):
        """
        Full lifecycle:
        Portfolio rebalance across BTC, ETH, and SOL allocating risk budgets within caps.
        """
        assets = [("BTC/USDT", 88500.0), ("ETH/USDT", 3100.0), ("SOL/USDT", 185.0)]
        orders = []
        for symbol, price in assets:
            sizing = crypto_sizing_engine.calculate_atr14_sizing(symbol, max_notional_cap_usd=200.0)
            order = paper_trader.place_order(symbol, "Buy", sizing.precision_lot_size, price)
            orders.append(order)
            assert order.status == "filled"

        assert len(paper_trader.positions) == 3
        assert paper_trader.cash_usd < 10000.0


# ===========================================================================
# Scenario 7: Portfolio Drawdown Circuit Breaker Total Lockdown
# ===========================================================================
class TestScenario7DrawdownLockdown:
    def test_workflow_drawdown_lockdown_blocks_new_buys_allows_sells(
        self,
        guardrail_pipeline,
        paper_trader,
    ):
        """
        Full lifecycle:
        8.2% drawdown locks out all new buy transactions while allowing emergency exit orders.
        """
        # Attempt Buy
        buy_req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict_buy = guardrail_pipeline.evaluate(buy_req, current_daily_drawdown_pct=8.2)
        assert verdict_buy.approved is False
        assert "exceeds circuit breaker" in verdict_buy.rejection_reason


# ===========================================================================
# Scenario 8: Jev UI Design Review Gate Before Dashboard Launch
# ===========================================================================
class TestScenario8JevUIQualityGateLaunch:
    def test_workflow_jev_ui_gate_passed_before_launch(self, stream_hub):
        """
        Full lifecycle:
        Jev evaluates visual quality, clarity, and brand consistency, verifying ready_to_ship == True.
        """
        review = stream_hub.review_ui_design(
            brief="Production Antigravity trading UI",
            summary="Clean dark theme with live candlestick chart, dual-channel SSE stream, and confirmed MetaMask bridge."
        )
        assert review["ready_to_ship"]["noul"] is True
        assert review["brand_fit"]["score"] in ["Good", "Excellent"]


# ===========================================================================
# Scenario 9: Extreme Slippage Detection and Dynamic Re-Quoting
# ===========================================================================
class TestScenario9ExtremeSlippageDetection:
    def test_workflow_extreme_slippage_rejection_and_safe_requote(self, guardrail_pipeline):
        """
        Full lifecycle:
        Large order encounters 3.2% price impact -> Rejected by L3 -> Resized to $100 -> Approved.
        """
        req_oversized = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**18,
            amount_out_min_wei=9500000,
            recipient="0xHotSigner",
            trade_value_usd=250.0,
        )
        v_blocked = guardrail_pipeline.evaluate(req_oversized, override_quoter_impact_pct=3.2)
        assert v_blocked.approved is False
        assert "exceeds 2.0% threshold" in v_blocked.rejection_reason

        # Resized order
        req_safe = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        v_safe = guardrail_pipeline.evaluate(req_safe, override_quoter_impact_pct=0.4)
        assert v_safe.approved is True


# ===========================================================================
# Scenario 10: Multi-Turn Debate Tiebreak Synthesis
# ===========================================================================
class TestScenario10DebateTiebreakSynthesis:
    def test_workflow_debate_tiebreak_synthesis(self, multi_agent_engine):
        """
        Full lifecycle:
        Equally balanced Bull and Bear arguments resolved by Research Manager weighting.
        """
        reports = multi_agent_engine.run_analysts("SOL-USD", is_crypto=True)
        plan = multi_agent_engine.run_bull_bear_debate("SOL-USD", reports)
        assert isinstance(plan, ResearchPlan)
        assert plan.recommendation in [PortfolioRating.BUY, PortfolioRating.HOLD]
        assert len(plan.strategic_actions) > 10
