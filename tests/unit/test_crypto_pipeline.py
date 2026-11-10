"""Unit Test Suite for Cryptocurrency Deliberation & Remote Agent Pipeline (Milestone 4 — F19–F23)."""
from __future__ import annotations

import json
import pytest

from crypto_pipeline import (
    AlternativeMeFearGreedFeed,
    ATRSizingEngine,
    CCXTMarketFeed,
    CryptoDeliberationPipeline,
    DeFiLlamaTVLFeed,
    JevCryptoDecisionScorer,
    RemoteAgentDeliberationBridge,
)
from tests.e2e.contracts import ATRSizingResult, CryptoRecommendation


class TestCCXTAndPublicFeeds:
    def test_ccxt_tickers_and_orderbook(self):
        feed = CCXTMarketFeed("binance", offline_mode=True)
        for sym in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            ticker = feed.fetch_ticker(sym)
            assert ticker["symbol"] == sym
            assert ticker["last"] > 0
            assert ticker["bid"] < ticker["ask"]
            ob = feed.fetch_order_book(sym, limit=5)
            assert len(ob["bids"]) == 5
            assert len(ob["asks"]) == 5

    def test_ccxt_ohlcv_and_precision(self):
        feed = CCXTMarketFeed("binance", offline_mode=True)
        candles = feed.fetch_ohlcv("BTC/USDT", limit=14)
        assert len(candles) == 14
        assert feed.amount_to_precision("BTC/USDT", 0.12345678) == "0.12345"
        assert feed.amount_to_precision("ETH/USDT", 1.234567) == "1.2345"
        assert feed.amount_to_precision("SOL/USDT", 12.349) == "12.34"

    def test_fear_and_greed_classifications(self):
        fng = AlternativeMeFearGreedFeed(offline_mode=True)
        assert fng.fetch_fear_and_greed(15)["data"][0]["value_classification"] == "Extreme Fear"
        assert fng.fetch_fear_and_greed(35)["data"][0]["value_classification"] == "Fear"
        assert fng.fetch_fear_and_greed(50)["data"][0]["value_classification"] == "Neutral"
        assert fng.fetch_fear_and_greed(68)["data"][0]["value_classification"] == "Greed"
        assert fng.fetch_fear_and_greed(85)["data"][0]["value_classification"] == "Extreme Greed"

    def test_defillama_tvl_map(self):
        tvl = DeFiLlamaTVLFeed(offline_mode=True)
        tvl_map = tvl.get_chain_tvl_map()
        assert tvl_map["Ethereum"] > 50e9
        assert tvl_map["Solana"] > 5e9
        assert tvl_map["Arbitrum"] > 1e9
        assert tvl_map["Base"] > 1e9


class TestATRSizingEngine:
    def test_atr14_sizing_and_cap(self):
        sizer = ATRSizingEngine()
        res = sizer.calculate_atr14_sizing(
            "BTC/USDT",
            portfolio_value_usd=100000.0,
            risk_pct_budget=0.01,
            multiplier=1.5,
            max_notional_cap_usd=250.0,
        )
        assert isinstance(res, ATRSizingResult)
        assert res.recommended_position_usd == 250.0
        assert res.capped_by_max_notional is True
        assert res.precision_lot_size > 0

    def test_atr14_rejects_invalid_inputs(self):
        sizer = ATRSizingEngine()
        with pytest.raises(ValueError):
            sizer.calculate_atr14_sizing("BTC/USDT", portfolio_value_usd=-100.0)
        with pytest.raises(ValueError):
            sizer.calculate_atr14_sizing("BTC/USDT", multiplier=0.0)
        with pytest.raises(ValueError):
            sizer.calculate_atr14_sizing("BTC/USDT", risk_pct_budget=float("nan"))


class TestRemoteAgentBridgeAndPipeline:
    def test_remote_agent_cli_command_format(self):
        cmd = RemoteAgentDeliberationBridge.build_command("Analyze BTC", "json")
        assert cmd[:3] == ["agy", "--remote-agent", "-p"]
        assert "--output-format" in cmd

    def test_remote_agent_execution_and_json_isolation(self):
        bridge = RemoteAgentDeliberationBridge()
        code, stdout, stderr = bridge.run_remote_deliberation("BTC", "Analyze BTC")
        assert code == 0
        assert "INFO:" in stderr
        parsed = json.loads(stdout)
        assert parsed["turn_count"] >= 1
        rec = bridge.execute_and_parse("BTC")
        assert isinstance(rec, CryptoRecommendation)
        assert rec.symbol == "BTC"
        assert rec.rating == "Buy"

    def test_full_crypto_deliberation_pipeline_and_jev_ranking(self):
        pipeline = CryptoDeliberationPipeline(offline_mode=True)
        report = pipeline.evaluate_major_cryptos()
        assert report["top_recommendation"] == "BTC"
        assert len(report["recommendations"]) == 3
        symbols = [r["symbol"] for r in report["recommendations"]]
        assert symbols == ["BTC", "ETH", "SOL"]
        for sym in ["BTC", "ETH", "SOL"]:
            assert report["jev_risk_verdicts"][sym]["verdict"]["choice"] == "APPROVE"

    def test_jev_scorer_rejects_excessive_drawdown(self):
        scorer = JevCryptoDecisionScorer()
        res = scorer.evaluate_trade_risk("BTC-USD", current_drawdown=0.10, risk_limit=0.08)
        assert res["verdict"]["choice"] == "REJECT"
