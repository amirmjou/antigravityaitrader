"""ATR-14 Volatility-Adjusted Position Sizing Engine (Feature F20).

Implements fixed-fractional risk budgeting:
    Dollar Risk = Portfolio Value * Risk Budget (%)
    Stop Distance = Multiplier * ATR_14
    Raw Lot Size = Dollar Risk / Stop Distance
    Notional USD = min(Raw Lot Size * Price, Max Notional Cap USD)
    Precision Lot Size = exchange.amount_to_precision(symbol, Raw Lot Size)
"""
from __future__ import annotations

import math
from typing import List, Optional

from crypto_pipeline.ingestion.feeds import CCXTMarketFeed
from tests.e2e.contracts import ATRSizingResult


class ATRSizingEngine:
    """Computes ATR-14 volatility-adjusted position sizes with exchange step precision."""

    def __init__(self, exchange: Optional[CCXTMarketFeed] = None):
        self.exchange = exchange or CCXTMarketFeed("binance")

    @staticmethod
    def compute_atr14_from_candles(candles: List[List[float]]) -> float:
        """Compute 14-period Average True Range from OHLCV candles."""
        if not candles or len(candles) < 2:
            raise ValueError("At least 2 OHLCV candles are required to compute ATR")
        tr_list: List[float] = []
        for i in range(1, len(candles)):
            high = float(candles[i][2])
            low = float(candles[i][3])
            prev_close = float(candles[i - 1][4])
            if not (math.isfinite(high) and math.isfinite(low) and math.isfinite(prev_close)):
                raise ValueError("Non-finite price encountered in OHLCV candles")
            if high < low or high <= 0 or low <= 0 or prev_close <= 0:
                raise ValueError("Invalid OHLCV candle bounds")
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list)
        if not math.isfinite(atr) or atr <= 0:
            raise ValueError(f"Computed invalid ATR: {atr}")
        return atr

    def calculate_atr14_sizing(
        self,
        symbol: str,
        portfolio_value_usd: float = 10000.0,
        risk_pct_budget: float = 0.01,
        multiplier: float = 1.5,
        max_notional_cap_usd: float = 250.0,
    ) -> ATRSizingResult:
        """Calculate volatility-adjusted position size for a crypto pair."""
        for name, val in [
            ("portfolio_value_usd", portfolio_value_usd),
            ("risk_pct_budget", risk_pct_budget),
            ("multiplier", multiplier),
            ("max_notional_cap_usd", max_notional_cap_usd),
        ]:
            if not math.isfinite(val) or val <= 0:
                raise ValueError(f"{name} must be a positive finite number, got {val}")

        if risk_pct_budget > 1.0:
            raise ValueError("risk_pct_budget must be <= 1.0 (100%)")

        candles = self.exchange.fetch_ohlcv(symbol, timeframe="1h", limit=14)
        atr_14 = self.compute_atr14_from_candles(candles)
        price = float(candles[-1][4])
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"Invalid latest close price: {price}")

        dollar_risk = portfolio_value_usd * risk_pct_budget
        stop_distance = atr_14 * multiplier
        raw_position_size = dollar_risk / stop_distance
        recommended_position_usd = raw_position_size * price

        capped = False
        if recommended_position_usd > max_notional_cap_usd:
            recommended_position_usd = max_notional_cap_usd
            raw_position_size = recommended_position_usd / price
            capped = True

        precision_str = self.exchange.amount_to_precision(symbol, raw_position_size)
        precision_lot = float(precision_str)

        return ATRSizingResult(
            symbol=symbol,
            portfolio_value_usd=portfolio_value_usd,
            risk_pct_budget=risk_pct_budget,
            atr_14=atr_14,
            multiplier=multiplier,
            dollar_risk=dollar_risk,
            recommended_position_usd=recommended_position_usd,
            raw_lot_size=raw_position_size,
            precision_lot_size=precision_lot,
            capped_by_max_notional=capped,
        )
