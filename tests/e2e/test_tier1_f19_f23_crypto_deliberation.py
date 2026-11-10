"""
Tier 1: Feature Coverage (Category-Partition)
Features F19–F23: Cryptocurrency Deliberation & Remote Agent Recommendation Pipeline (Milestone 4)
Each feature has >= 5 comprehensive, requirement-driven test cases.
"""
import pytest

from tests.e2e.contracts import ATRSizingResult, CryptoRecommendation
from tests.e2e.fixtures import (
    LocalJevMCPClient,
    MockCCXTExchange,
    MockPublicAPIs,
    MockRemoteAgentBridge,
)
from tests.e2e.harness import CryptoIngestionSizingEngine


# ===========================================================================
# Feature F19: Crypto Data Ingestion Feeds
# ===========================================================================
class TestF19CryptoDataIngestionFeeds:
    def test_f19_01_ccxt_major_crypto_tickers(self, crypto_sizing_engine):
        """Verify CCXT ticker retrieval for BTC, ETH, SOL."""
        for sym in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            ticker = crypto_sizing_engine.exchange.fetch_ticker(sym)
            assert ticker["symbol"] == sym
            assert ticker["last"] > 0
            assert ticker["bid"] <= ticker["ask"]

    def test_f19_02_ccxt_ohlcv_14_period_lookback(self, crypto_sizing_engine):
        """Verify OHLCV fetching returns 14 candles with valid time ordering."""
        candles = crypto_sizing_engine.exchange.fetch_ohlcv("BTC/USDT", limit=14)
        assert len(candles) == 14
        for i in range(1, len(candles)):
            assert candles[i][0] > candles[i - 1][0]  # Monotonic timestamp

    def test_f19_03_alternative_me_fear_and_greed_feed(self):
        """Verify Alternative.me Fear & Greed index parsing."""
        fng = MockPublicAPIs.get_fear_and_greed(override_value=72)
        assert fng["name"] == "Crypto Fear & Greed Index"
        val = int(fng["data"][0]["value"])
        assert 0 <= val <= 100
        assert fng["data"][0]["value_classification"] == "Greed"

    def test_f19_04_defillama_chain_tvl_ingestion(self):
        """Verify DeFiLlama TVL data ingestion for supported chains."""
        chains = MockPublicAPIs.get_defillama_chains()
        chain_map = {c["name"]: c["tvl"] for c in chains}
        assert "Ethereum" in chain_map
        assert "Arbitrum" in chain_map
        assert "Base" in chain_map
        assert chain_map["Arbitrum"] > 1e9  # > $1B TVL

    def test_f19_05_exchange_rate_limit_enabled(self, crypto_sizing_engine):
        """Verify rate limit throttling is active on exchange instances."""
        assert crypto_sizing_engine.exchange.enableRateLimit is True
        assert crypto_sizing_engine.exchange.rateLimit >= 1000


# ===========================================================================
# Feature F20: Volatility-Adjusted Sizing
# ===========================================================================
class TestF20VolatilityAdjustedSizing:
    def test_f20_01_atr14_calculation_accuracy(self, crypto_sizing_engine):
        """Verify ATR-14 volatility computation."""
        res = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT")
        assert res.atr_14 > 0.0
        assert isinstance(res, ATRSizingResult)

    def test_f20_02_fixed_fractional_risk_formula(self, crypto_sizing_engine):
        """Verify position sizing inversely scales with stop distance."""
        res_tight = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", multiplier=1.0, max_notional_cap_usd=10000.0)
        res_wide = crypto_sizing_engine.calculate_atr14_sizing("BTC/USDT", multiplier=2.0, max_notional_cap_usd=10000.0)
        # Wider stop distance must result in smaller raw lot size
        assert res_wide.raw_lot_size < res_tight.raw_lot_size

    def test_f20_03_lot_precision_formatting_btc(self, crypto_sizing_engine):
        """Verify Bitcoin lot size conforms to 5 decimal places precision."""
        prec_str = crypto_sizing_engine.exchange.amount_to_precision("BTC/USDT", 0.12345678)
        assert len(prec_str.split(".")[1]) == 5
        assert prec_str == "0.12345"

    def test_f20_04_lot_precision_formatting_sol(self, crypto_sizing_engine):
        """Verify Solana lot size conforms to 2 decimal places precision."""
        prec_str = crypto_sizing_engine.exchange.amount_to_precision("SOL/USDT", 1.239)
        assert len(prec_str.split(".")[1]) == 2
        assert prec_str == "1.23"

    def test_f20_05_max_notional_cap_bounding(self, crypto_sizing_engine):
        """Verify positions exceeding max notional spend ($250 default) are bounded."""
        res = crypto_sizing_engine.calculate_atr14_sizing(
            "BTC/USDT",
            portfolio_value_usd=100000.0,  # 1% risk = $1000
            max_notional_cap_usd=250.0,
        )
        assert res.recommended_position_usd == 250.0
        assert res.capped_by_max_notional is True


# ===========================================================================
# Feature F21: Remote Agent Deliberation Bridge
# ===========================================================================
class TestF21RemoteAgentDeliberationBridge:
    def test_f21_01_remote_agent_execution_success(self, crypto_sizing_engine):
        """Verify agy --remote-agent non-interactive execution returns valid recommendation."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        assert isinstance(rec, CryptoRecommendation)
        assert rec.symbol == "BTC"
        assert rec.rating in ["Buy", "Hold", "Sell"]

    def test_f21_02_remote_agent_stdout_json_isolation(self):
        """Verify stdout contains pure JSON while diagnostic logs route to stderr."""
        bridge = MockRemoteAgentBridge()
        code, stdout, stderr = bridge.run_remote_deliberation("ETH", "Deliberate")
        assert code == 0
        assert stdout.startswith("{") and stdout.endswith("}")
        assert "INFO:" in stderr

    def test_f21_03_remote_agent_timeout_handling(self):
        """Verify timeout raises informative error without corrupting state."""
        bridge = MockRemoteAgentBridge(should_fail=True, failure_mode="timeout")
        engine = CryptoIngestionSizingEngine()
        engine.remote_bridge = bridge
        with pytest.raises(RuntimeError) as exc_info:
            engine.execute_remote_agent("BTC")
        assert "timed out" in str(exc_info.value)

    def test_f21_04_remote_agent_malformed_json_fallback(self):
        """Verify malformed JSON from remote stream raises clean parse error."""
        bridge = MockRemoteAgentBridge(should_fail=True, failure_mode="malformed_json")
        engine = CryptoIngestionSizingEngine()
        engine.remote_bridge = bridge
        with pytest.raises(Exception):
            engine.execute_remote_agent("SOL")

    def test_f21_05_remote_agent_metadata_tracking(self):
        """Verify duration and token usage are present in remote agent execution."""
        bridge = MockRemoteAgentBridge()
        _, stdout, _ = bridge.run_remote_deliberation("BTC", "Deliberate")
        import json
        payload = json.loads(stdout)
        assert payload["duration_ms"] > 0
        assert payload["token_usage"]["total"] > 0


# ===========================================================================
# Feature F22: Production Crypto Recommendations
# ===========================================================================
class TestF22ProductionCryptoRecommendations:
    def test_f22_01_btc_production_recommendation(self, crypto_sizing_engine):
        """Verify explicit Buy/Sell/Hold rating for BTC."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        assert rec.symbol == "BTC"
        assert rec.rating in ["Buy", "Hold", "Sell"]
        assert rec.position_size_usd <= 250.0

    def test_f22_02_eth_production_recommendation(self, crypto_sizing_engine):
        """Verify explicit recommendation and thesis for ETH."""
        rec = crypto_sizing_engine.execute_remote_agent("ETH")
        assert rec.symbol == "ETH"
        assert len(rec.bull_argument) > 10
        assert len(rec.bear_argument) > 10

    def test_f22_03_sol_production_recommendation(self, crypto_sizing_engine):
        """Verify explicit recommendation and risk levels for SOL."""
        rec = crypto_sizing_engine.execute_remote_agent("SOL")
        assert rec.symbol == "SOL"
        assert rec.stop_loss_pct > 0.0

    def test_f22_04_bull_vs_bear_argument_completeness(self, crypto_sizing_engine):
        """Verify both Bull and Bear arguments are provided in recommendation."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        assert "institutional" in rec.bull_argument.lower() or "momentum" in rec.bull_argument.lower()
        assert "rsi" in rec.bear_argument.lower() or "overbought" in rec.bear_argument.lower()

    def test_f22_05_entry_target_specification(self, crypto_sizing_engine):
        """Verify entry price target is populated."""
        rec = crypto_sizing_engine.execute_remote_agent("BTC")
        assert rec.entry_target_usd is not None
        assert rec.entry_target_usd > 50000.0


# ===========================================================================
# Feature F23: Jev Deterministic Decision Scoring
# ===========================================================================
class TestF23JevDeterministicDecisionScoring:
    def test_f23_01_jev_decide_approval(self, jev_client):
        """Verify jev_decide approves trade within risk parameters."""
        res = jev_client.decide(
            state={"symbol": "BTC-USD", "drawdown": 0.02, "risk_limit": 0.08},
            questions={"verdict": {"type": "choice"}}
        )
        assert res["verdict"]["choice"] == "APPROVE"
        assert res["verdict"]["confidence"] >= 0.80

    def test_f23_02_jev_decide_drawdown_rejection(self, jev_client):
        """Verify jev_decide rejects trade when drawdown exceeds risk limit."""
        res = jev_client.decide(
            state={"symbol": "BTC-USD", "drawdown": 0.09, "risk_limit": 0.08},
            questions={"verdict": {"type": "choice"}}
        )
        assert res["verdict"]["choice"] == "REJECT"

    def test_f23_03_jev_pick_variant_selection(self, jev_client):
        """Verify jev_pick_variant scores and selects winning strategy variant."""
        variants = {
            "atr_trailing_stop": "Use 1.5x ATR trailing stop with 5% allocation",
            "fixed_stop": "Use fixed 2% stop-loss with 3% allocation"
        }
        res = jev_client.pick_variant("BTC breakout execution strategy", variants)
        assert res["best_variant"]["choice"] in variants
        assert res["best_variant"]["confidence"] > 0.0

    def test_f23_04_jev_status_offline_ready(self, jev_client):
        """Verify Jev engine operates in on-premise offline mode without external API keys."""
        assert jev_client.mode == "on-premise-offline"

    def test_f23_05_jev_noul_boolean_scoring(self, jev_client):
        """Verify Jev evaluates noul type boolean likelihoods."""
        res = jev_client.decide(
            state={"signal": "strong_bullish_cross"},
            questions={"should_execute": {"type": "noul"}}
        )
        assert res["should_execute"]["type"] == "noul"
        assert isinstance(res["should_execute"]["noul"], bool)
        assert 0.0 <= res["should_execute"]["probability"] <= 1.0
