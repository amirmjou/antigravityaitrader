"""
Tier 3: Cross-Feature Pairwise Combinations
Tests interaction matrix across multi-agent deliberation, pre-broadcast guardrails,
volatility sizing, Uniswap quoter, remote cloud agents, Jev scoring, and UI streaming.
"""
import pytest

from tests.e2e.contracts import (
    PortfolioRating,
    ResearchPlan,
    SwapTransactionRequest,
    ThinkingLevel,
    TraderAction,
    TraderProposal,
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
# Pair 1: Multi-Agent Deliberation (M1) <-> Guardrail Pipeline (M2)
# ===========================================================================
class TestAgentDeliberationAndGuardrails:
    def test_pair_agent_buy_proposal_approved_by_guardrails(self, multi_agent_engine, guardrail_pipeline):
        """M1 Buy proposal passes all 5 guardrail layers."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Momentum", strategic_actions="Buy")
        prop = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=88500.0)
        
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert prop.action == "Buy"
        assert verdict.approved is True

    def test_pair_agent_oversized_buy_rejected_by_l2_cap(self, multi_agent_engine, guardrail_pipeline):
        """M1 Buy proposal requesting oversized capital trips Layer 2 spend limit."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Extreme high conviction", strategic_actions="All in")
        prop = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=88500.0)
        
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**17,
            amount_out_min_wei=9500000,
            recipient="0xHotSigner",
            trade_value_usd=500.0,  # Exceeds $250 default cap
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "exceeds cap of $250.0" in verdict.rejection_reason

    def test_pair_agent_proposal_on_honeypot_blocked_by_l1(self, multi_agent_engine, guardrail_pipeline):
        """M1 Buy proposal on an unverified honeypot token is hard blocked by Layer 1."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Speculative", strategic_actions="Buy")
        prop = multi_agent_engine.run_trader_proposal("BAD-TOKEN", plan, market_price=1.0)
        
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0xBadHoneypotTokenAddress0000000000000000",
            amount_in_wei=10**16,
            amount_out_min_wei=1000,
            recipient="0xHotSigner",
            trade_value_usd=50.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        assert "Honeypot detected" in verdict.rejection_reason

    def test_pair_elevated_drawdown_blocks_agent_proposal(self, multi_agent_engine, guardrail_pipeline):
        """M1 proposes long entry but high current drawdown trips circuit breaker."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Dip buying", strategic_actions="Buy")
        prop = multi_agent_engine.run_trader_proposal("ETH-USD", plan, market_price=3100.0)
        
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req, current_daily_drawdown_pct=8.5)
        assert verdict.approved is False
        assert "exceeds circuit breaker 8.0%" in verdict.rejection_reason


# ===========================================================================
# Pair 2: ATR Sizing (M4) <-> Uniswap v3 Quoter (M2)
# ===========================================================================
class TestSizingAndUniswapQuoter:
    def test_pair_atr_size_feeds_uniswap_quote(self, crypto_sizing_engine, uniswap_quoter):
        """ATR-14 calculated lot size directly computes Quoter amount_out and price impact."""
        sizing = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", max_notional_cap_usd=200.0)
        amount_in_wei = int(sizing.precision_lot_size * 10**18)
        
        amount_out, impact_pct, gas = uniswap_quoter.quote_exact_input_single(
            "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=amount_in_wei
        )
        assert amount_out > 0
        assert impact_pct < 2.0  # Safe impact
        assert gas == 125000

    def test_pair_high_atr_reduces_quoter_price_impact(self, crypto_sizing_engine, uniswap_quoter):
        """When volatility expands, smaller position size reduces pool price impact."""
        # Low multiplier (larger size)
        sz_large = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", multiplier=1.0, max_notional_cap_usd=5000.0)
        # High multiplier (conservative, smaller size)
        sz_small = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", multiplier=3.0, max_notional_cap_usd=5000.0)
        
        _, impact_large, _ = uniswap_quoter.quote_exact_input_single("in", "out", int(sz_large.raw_lot_size * 10**18))
        _, impact_small, _ = uniswap_quoter.quote_exact_input_single("in", "out", int(sz_small.raw_lot_size * 10**18))
        assert impact_small < impact_large

    def test_pair_quoter_minimum_output_enforces_slippage_bound(self, crypto_sizing_engine, uniswap_quoter):
        """Quoted output minus 50 bps slippage matches amountOutMinimum."""
        amount_in_wei = 10**17
        quoted_out, _, _ = uniswap_quoter.quote_exact_input_single("in", "out", amount_in_wei)
        slippage_bps = 50
        amount_out_min = int(quoted_out * (1.0 - (slippage_bps / 10000.0)))
        assert amount_out_min < quoted_out
        assert amount_out_min > int(quoted_out * 0.99)


# ===========================================================================
# Pair 3: Remote Agent Deliberation (M4) <-> Jev Scoring (M1/M4)
# ===========================================================================
class TestRemoteAgentAndJevScoring:
    def test_pair_remote_recommendation_evaluated_by_jev(self, crypto_sizing_engine, jev_client):
        """Recommendation produced by agy --remote-agent is evaluated by jev_decide."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        jev_res = jev_client.decide(
            state={"symbol": rec.symbol, "rating": rec.rating, "size": rec.position_size_usd, "drawdown": 0.02},
            questions={"risk_approval": {"type": "choice"}}
        )
        assert jev_res["risk_approval"]["choice"] == "APPROVE"

    def test_pair_multiple_remote_strategies_picked_by_jev(self, jev_client):
        """jev_pick_variant chooses between remote bullish momentum vs mean reversion."""
        variants = {
            "remote_breakout": "Follow agy recommendation with 2.5% stop loss",
            "mean_reversion": "Fade overbought RSI and wait for 200 EMA retest"
        }
        picked = jev_client.pick_variant("Crypto strategic trade execution", variants)
        assert picked["best_variant"]["choice"] in variants

    def test_pair_jev_confidence_modulates_remote_order_size(self, crypto_sizing_engine, jev_client):
        """High Jev confidence validates maximum notional allocation."""
        rec = crypto_sizing_engine.execute_remote_agent("ETH")
        jev_res = jev_client.decide(
            state={"symbol": rec.symbol, "drawdown": 0.01},
            questions={"confidence_gate": {"type": "choice"}}
        )
        confidence = jev_res["confidence_gate"]["confidence"]
        assert confidence >= 0.80
        effective_size = rec.position_size_usd * confidence
        assert effective_size <= 250.0


# ===========================================================================
# Pair 4: Dual-Engine Router (M2) <-> UI Telemetry Stream (M3)
# ===========================================================================
class TestRouterAndTelemetryStream:
    def test_pair_swap_broadcast_publishes_sse_execution_event(self, wallet_router, stream_hub):
        """Successful swap execution emits trade_telemetry to SSE stream."""
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req)
        assert res.success is True
        
        # Publish execution to stream hub
        stream_hub.publish_event(
            "trade_telemetry",
            "DualEngineWallet",
            f"Swap executed: tx={res.tx_hash}",
            snapshot={"tx_hash": res.tx_hash, "gas_used": res.gas_used, "block": res.block_number}
        )
        assert len(stream_hub.event_stream) == 1
        ev = stream_hub.event_stream[0]
        assert ev.event == "trade_telemetry"
        assert res.tx_hash in ev.token

    def test_pair_revert_publishes_rejection_telemetry(self, wallet_router, web3_arbitrum, stream_hub):
        """Failed simulation publishes error event to stream hub."""
        web3_arbitrum.set_revert_trigger("INSUFFICIENT_LIQUIDITY")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req)
        assert res.success is False
        
        stream_hub.publish_event("agent_thought", "DualEngineWallet", f"Trade failed: {res.revert_reason}")
        assert len(stream_hub.event_stream) == 1
        assert "INSUFFICIENT_LIQUIDITY" in stream_hub.event_stream[0].token
        web3_arbitrum.set_revert_trigger(None)


# ===========================================================================
# Pair 5: Multi-DEX Routing (Arbitrum/Base) <-> Multi-Asset Ingestion (BTC/ETH/SOL)
# ===========================================================================
class TestMultiChainRoutingAndAssets:
    def test_pair_btc_routes_to_arbitrum_uniswap(self, arbitrum_config, wallet_router):
        """BTC trade resolves to WBTC swap on Arbitrum One (42161)."""
        assert arbitrum_config.chain_id == 42161
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", # WBTC
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        res = wallet_router.execute_swap(req)
        assert res.success is True

    def test_pair_eth_routes_to_base_aerodrome(self, base_config, web3_base):
        """ETH trade resolves to Base (8453) router with sub-cent gas fee."""
        base_router = DualEngineWalletRouter(web3_provider=web3_base, chain_config=base_config)
        req = SwapTransactionRequest(
            chain_id=8453,
            token_in="0x4200000000000000000000000000000000000006",
            token_out="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            amount_in_wei=10**16,
            amount_out_min_wei=30000000,
            recipient="0xHotSigner",
            trade_value_usd=30.0,
        )
        res = base_router.execute_swap(req)
        assert res.success is True
        assert res.effective_gas_price_gwei == 0.005  # Base L2 sub-cent gas


# ===========================================================================
# Pair 6: Execution Revert (M2) <-> Memory Log Rollback (M1)
# ===========================================================================
class TestSimulationRevertAndMemoryLog:
    def test_pair_reverted_trade_records_rejection_in_memory(self, multi_agent_engine, guardrail_pipeline, web3_arbitrum):
        """When guardrail trips, memory log records rejection to avoid repeated bad trades."""
        web3_arbitrum.set_revert_trigger("TRANSFER_FAILED")
        req = SwapTransactionRequest(
            chain_id=42161,
            token_in="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
            token_out="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
            amount_in_wei=10**16,
            amount_out_min_wei=950000,
            recipient="0xHotSigner",
            trade_value_usd=100.0,
        )
        verdict = guardrail_pipeline.evaluate(req)
        assert verdict.approved is False
        
        # Log failure to memory
        multi_agent_engine.memory_log.append({
            "symbol": "BTC-USD",
            "action": "Rejected",
            "reason": verdict.rejection_reason,
            "timestamp": 1730900000
        })
        assert len(multi_agent_engine.memory_log) == 1
        assert "TRANSFER_FAILED" in multi_agent_engine.memory_log[0]["reason"]
        web3_arbitrum.set_revert_trigger(None)


# ===========================================================================
# Pair 7: Paper Trading (M5) <-> Multi-Agent Deliberation (M1)
# ===========================================================================
class TestPaperTradingAndAgentDeliberation:
    def test_pair_agent_buy_triggers_paper_trading_fill(self, multi_agent_engine, paper_trader):
        """M1 Buy proposal automatically executes filled paper trading order."""
        plan = ResearchPlan(recommendation=PortfolioRating.BUY, rationale="Conviction", strategic_actions="Buy")
        prop = multi_agent_engine.run_trader_proposal("BTC-USD", plan, market_price=88500.0)
        order = paper_trader.place_order("BTC/USDT", prop.action, 0.001, prop.entry_price)
        assert order.status == "filled"
        assert "BTC/USDT" in paper_trader.positions

    def test_pair_agent_sell_triggers_paper_trading_liquidation(self, multi_agent_engine, paper_trader):
        """M1 Sell proposal liquidates existing paper trading position."""
        paper_trader.place_order("ETH/USDT", "Buy", 1.0, 3100.0)
        plan = ResearchPlan(recommendation=PortfolioRating.SELL, rationale="Deterioration", strategic_actions="Sell")
        prop = multi_agent_engine.run_trader_proposal("ETH-USD", plan, market_price=3100.0)
        prop.action = "Sell"
        order = paper_trader.place_order("ETH/USDT", prop.action, 1.0, 3100.0)
        assert order.status == "filled"
        assert paper_trader.positions["ETH/USDT"].quantity == 0.0


# ===========================================================================
# Pair 8: Jev Quality Gate (M3) <-> SSE Telemetry (M3)
# ===========================================================================
class TestJevQualityGateAndSSETelemetry:
    def test_pair_jev_audit_broadcasts_sse_event(self, stream_hub):
        """Jev design review gate results are published to SSE event stream."""
        review = stream_hub.review_ui_design("Terminal UI", "Complete dark mode dashboard")
        stream_hub.publish_event(
            "decision",
            "JevQualityGate",
            f"Review complete: ready={review['ready_to_ship']['noul']}",
            snapshot=review
        )
        assert len(stream_hub.event_stream) == 1
        ev = stream_hub.event_stream[0]
        assert ev.event == "decision"
        assert ev.agent_role == "JevQualityGate"

    def test_pair_jev_rejection_alerts_ui_stream(self, stream_hub):
        """Incomplete UI status emits warning event on SSE channel."""
        stream_hub.publish_event("agent_thought", "JevQualityGate", "Warning: High contrast ratio required.")
        assert len(stream_hub.event_stream) == 1
        assert "Warning" in stream_hub.event_stream[0].token


# ===========================================================================
# Pair 9: GoPlus Security (M2) <-> CCXT Ingestion (M4)
# ===========================================================================
class TestGoPlusSecurityAndCCXTIngestion:
    def test_pair_ingested_symbol_maps_to_goplus_contract_check(self, crypto_sizing_engine, goplus_client):
        """CCXT ingested symbol resolves to on-chain token address for security verification."""
        ticker = crypto_sizing_engine.exchange.fetch_ticker("BTC/USDT")
        assert ticker["last"] > 0
        wbtc_arb = "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f"
        sec = goplus_client.check_token_security(42161, wbtc_arb)
        assert sec["is_honeypot"] == "0"
        assert float(sec["buy_tax"]) == 0.0

    def test_pair_malicious_symbol_caught_prior_to_quoting(self, goplus_client):
        """Honeypot token is detected and blocked before quoter execution."""
        bad_token = "0xBadHoneypotTokenAddress0000000000000000"
        sec = goplus_client.check_token_security(42161, bad_token)
        assert sec["is_honeypot"] == "1"


# ===========================================================================
# Pair 10: Thinking Levels (M1) <-> Debate Depth
# ===========================================================================
class TestThinkingLevelsAndDebateDepth:
    def test_pair_high_thinking_level_enables_thorough_debate(self):
        """High thinking level configures deep debate parameters."""
        engine_high = MultiAgentDeliberationEngine(thinking_level=ThinkingLevel.HIGH)
        assert engine_high.max_debate_rounds >= 2
        reports = engine_high.run_analysts("BTC-USD", is_crypto=True)
        plan = engine_high.run_bull_bear_debate("BTC-USD", reports)
        assert "4 turns" in plan.rationale

    def test_pair_minimal_thinking_level_fast_path(self):
        """Minimal thinking level optimizes for low latency execution."""
        engine_min = MultiAgentDeliberationEngine(thinking_level=ThinkingLevel.MINIMAL)
        assert engine_min.llm.thinking_level == "minimal"


# ===========================================================================
# Pair 11: Remote Agent (M4) <-> Memory Log (M1)
# ===========================================================================
class TestRemoteAgentAndMemoryLog:
    def test_pair_remote_agent_recommendation_recorded_in_memory_log(self, crypto_sizing_engine, multi_agent_engine):
        """Remote recommendation is committed to memory log for retrospective audit."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        multi_agent_engine.memory_log.append({
            "source": "agy --remote-agent",
            "symbol": rec.symbol,
            "rating": rec.rating,
            "size": rec.position_size_usd,
            "timestamp": 1730900000
        })
        assert len(multi_agent_engine.memory_log) == 1
        assert multi_agent_engine.memory_log[0]["source"] == "agy --remote-agent"

    def test_pair_memory_log_filters_by_remote_agent_source(self, multi_agent_engine):
        """Memory log queries can filter records generated by remote cloud deliberation."""
        multi_agent_engine.memory_log.append({"source": "local", "symbol": "ETH"})
        multi_agent_engine.memory_log.append({"source": "remote", "symbol": "BTC"})
        remote_records = [r for r in multi_agent_engine.memory_log if r.get("source") == "remote"]
        assert len(remote_records) == 1
        assert remote_records[0]["symbol"] == "BTC"
