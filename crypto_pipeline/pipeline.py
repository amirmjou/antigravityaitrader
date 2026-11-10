"""End-to-End Cryptocurrency Deliberation & Recommendation Pipeline (Milestone 4)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from crypto_pipeline.ingestion.feeds import (
    AlternativeMeFearGreedFeed,
    CCXTMarketFeed,
    DeFiLlamaTVLFeed,
)
from crypto_pipeline.jev_integration.scorer import JevCryptoDecisionScorer
from crypto_pipeline.remote_agent.bridge import RemoteAgentDeliberationBridge
from crypto_pipeline.sizing.atr_sizer import ATRSizingEngine
from tests.e2e.contracts import ATRSizingResult, CryptoRecommendation


class CryptoDeliberationPipeline:
    """Unified coordinator for F19–F23: Ingestion, ATR Sizing, Remote Agent, and Jev Scoring."""

    MAJOR_SYMBOLS = ("BTC", "ETH", "SOL")

    def __init__(
        self,
        exchange: Optional[CCXTMarketFeed] = None,
        fng_feed: Optional[AlternativeMeFearGreedFeed] = None,
        tvl_feed: Optional[DeFiLlamaTVLFeed] = None,
        remote_bridge: Optional[RemoteAgentDeliberationBridge] = None,
        jev_scorer: Optional[JevCryptoDecisionScorer] = None,
        offline_mode: bool = True,
    ):
        self.exchange = exchange or CCXTMarketFeed("binance", offline_mode=offline_mode)
        self.fng_feed = fng_feed or AlternativeMeFearGreedFeed(offline_mode=offline_mode)
        self.tvl_feed = tvl_feed or DeFiLlamaTVLFeed(offline_mode=offline_mode)
        self.sizer = ATRSizingEngine(exchange=self.exchange)
        self.remote_bridge = remote_bridge or RemoteAgentDeliberationBridge()
        self.jev_scorer = jev_scorer or JevCryptoDecisionScorer()

    def calculate_atr14_sizing(
        self,
        symbol: str,
        portfolio_value_usd: float = 10000.0,
        risk_pct_budget: float = 0.01,
        multiplier: float = 1.5,
        max_notional_cap_usd: float = 250.0,
    ) -> ATRSizingResult:
        """Delegate ATR-14 sizing computation."""
        return self.sizer.calculate_atr14_sizing(
            symbol=symbol,
            portfolio_value_usd=portfolio_value_usd,
            risk_pct_budget=risk_pct_budget,
            multiplier=multiplier,
            max_notional_cap_usd=max_notional_cap_usd,
        )

    def execute_remote_agent(self, symbol: str) -> CryptoRecommendation:
        """Execute `agy --remote-agent` deliberation for a single crypto symbol."""
        return self.remote_bridge.execute_and_parse(symbol)

    def evaluate_major_cryptos(
        self,
        symbols: Optional[List[str]] = None,
        portfolio_value_usd: float = 10000.0,
        max_notional_cap_usd: float = 250.0,
        current_drawdown: float = 0.02,
    ) -> Dict[str, Any]:
        """Run complete multi-agent & Jev analysis across BTC, ETH, and SOL."""
        target_symbols = symbols or list(self.MAJOR_SYMBOLS)
        fng_data = self.fng_feed.fetch_fear_and_greed()
        tvl_map = self.tvl_feed.get_chain_tvl_map()

        recommendations: List[CryptoRecommendation] = []
        sizing_map: Dict[str, Dict[str, Any]] = {}
        jev_verdicts: Dict[str, Dict[str, Any]] = {}

        for sym in target_symbols:
            pair = self.exchange.normalize_symbol(sym)
            ticker = self.exchange.fetch_ticker(pair)
            sizing = self.calculate_atr14_sizing(
                pair,
                portfolio_value_usd=portfolio_value_usd,
                max_notional_cap_usd=max_notional_cap_usd,
            )
            sizing_map[sym] = sizing.model_dump()

            prompt = (
                f"Deliberate on {sym} ({pair}) spot trading strategy. "
                f"Price=${ticker['last']}, ATR14=${sizing.atr_14:.2f}, "
                f"Fear&Greed={fng_data['data'][0]['value']} ({fng_data['data'][0]['value_classification']})."
            )
            rec = self.remote_bridge.execute_and_parse(sym, prompt=prompt)
            recommendations.append(rec)

            jev_verdicts[sym] = self.jev_scorer.evaluate_trade_risk(
                symbol=f"{sym}-USD",
                current_drawdown=current_drawdown,
                risk_limit=0.08,
                stop_loss_pct=rec.stop_loss_pct,
                position_size_usd=rec.position_size_usd,
            )

        ranking_result = self.jev_scorer.rank_crypto_candidates(recommendations)
        return {
            "market_sentiment": fng_data["data"][0],
            "chain_tvl_usd": tvl_map,
            "recommendations": [r.model_dump() for r in recommendations],
            "atr_sizing": sizing_map,
            "jev_risk_verdicts": jev_verdicts,
            "top_recommendation": ranking_result["top_pick_symbol"],
            "rankings": ranking_result["rankings"],
            "jev_variant_selection": ranking_result["best_variant"],
        }
