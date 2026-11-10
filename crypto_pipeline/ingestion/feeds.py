"""Multi-source cryptocurrency data ingestion feeds (Feature F19).

Integrates:
1. CCXT multi-exchange market data (OHLCV, Ticker, Order Book, Lot Precision)
2. Alternative.me Crypto Fear & Greed Index
3. DeFiLlama Chain TVL Fundamentals
Provides deterministic offline fallback for zero-key / air-gapped environments.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
import math
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_PRICES: Dict[str, float] = {
    "BTC/USDT": 88500.0,
    "ETH/USDT": 3120.0,
    "SOL/USDT": 185.0,
}

DEFAULT_PRECISION_DECIMALS: Dict[str, int] = {
    "BTC/USDT": 5,
    "ETH/USDT": 4,
    "SOL/USDT": 2,
}


class CCXTMarketFeed:
    """CCXT-compatible market feed with rate-limit enforcement and offline fallback."""

    def __init__(
        self,
        exchange_id: str = "binance",
        enable_rate_limit: bool = True,
        rate_limit_ms: int = 1000,
        offline_mode: bool = True,
    ):
        if rate_limit_ms < 0:
            raise ValueError("rate_limit_ms must be non-negative")
        self.exchange_id = exchange_id
        self.enableRateLimit = bool(enable_rate_limit)
        self.rateLimit = max(int(rate_limit_ms), 1000) if enable_rate_limit else int(rate_limit_ms)
        self.offline_mode = offline_mode
        self._base_prices: Dict[str, float] = dict(DEFAULT_BASE_PRICES)
        self._precision_map: Dict[str, int] = dict(DEFAULT_PRECISION_DECIMALS)
        self._ccxt_client = None

        if not self.offline_mode:
            try:
                import ccxt  # type: ignore

                exchange_cls = getattr(ccxt, exchange_id, None)
                if exchange_cls is not None:
                    self._ccxt_client = exchange_cls(
                        {"enableRateLimit": self.enableRateLimit, "rateLimit": self.rateLimit}
                    )
            except Exception:
                self._ccxt_client = None

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to BASE/USDT format."""
        s = (symbol or "").strip().upper()
        if not s:
            raise ValueError("Symbol cannot be empty")
        if "/" not in s:
            s = s.replace("-USD", "/USDT").replace("-USDT", "/USDT")
            if "/" not in s:
                s = f"{s}/USDT"
        return s

    def set_base_price(self, symbol: str, price: float) -> None:
        """Override base price for testing or simulation."""
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"Invalid base price: {price}")
        norm = self.normalize_symbol(symbol)
        self._base_prices[norm] = float(price)

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest ticker with bid/ask/last/volume."""
        norm = self.normalize_symbol(symbol)
        if self._ccxt_client is not None and not self.offline_mode:
            try:
                ticker = self._ccxt_client.fetch_ticker(norm)
                if ticker and ticker.get("last"):
                    return ticker
            except Exception:
                pass

        if norm not in self._base_prices:
            raise ValueError(f"Unsupported symbol: {symbol}")
        p = self._base_prices[norm]
        return {
            "symbol": norm,
            "timestamp": int(time.time() * 1000),
            "last": p,
            "close": p,
            "bid": round(p * 0.9995, 2),
            "ask": round(p * 1.0005, 2),
            "high": round(p * 1.025, 2),
            "low": round(p * 0.975, 2),
            "baseVolume": 14520.5,
            "quoteVolume": round(p * 14520.5, 2),
        }

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 14
    ) -> List[List[float]]:
        """Fetch historical OHLCV candles [timestamp_ms, open, high, low, close, volume]."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        norm = self.normalize_symbol(symbol)
        if self._ccxt_client is not None and not self.offline_mode:
            try:
                candles = self._ccxt_client.fetch_ohlcv(norm, timeframe=timeframe, limit=limit)
                if candles and len(candles) >= limit:
                    return candles[-limit:]
            except Exception:
                pass

        if norm not in self._base_prices:
            raise ValueError(f"Unsupported symbol: {symbol}")
        p = self._base_prices[norm]
        base_ts = 1730900000000 - (limit * 3600 * 1000)
        candles: List[List[float]] = []
        for i in range(limit):
            ts = base_ts + i * 3600 * 1000
            open_p = round(p * (1.0 + (i - limit / 2) * 0.001), 2)
            high_p = round(open_p * 1.012, 2)
            low_p = round(open_p * 0.988, 2)
            close_p = round(open_p * 1.002, 2)
            vol = round(1000.0 + i * 25.0, 2)
            candles.append([ts, open_p, high_p, low_p, close_p, vol])
        return candles

    def fetch_order_book(self, symbol: str, limit: int = 5) -> Dict[str, Any]:
        """Fetch L2 order book snapshot."""
        norm = self.normalize_symbol(symbol)
        if norm not in self._base_prices:
            raise ValueError(f"Unsupported symbol: {symbol}")
        p = self._base_prices[norm]
        bids = [[round(p * (1.0 - 0.0005 * (i + 1)), 2), round(1.5 * (i + 1), 4)] for i in range(limit)]
        asks = [[round(p * (1.0 + 0.0005 * (i + 1)), 2), round(1.2 * (i + 1), 4)] for i in range(limit)]
        return {
            "symbol": norm,
            "bids": bids,
            "asks": asks,
            "timestamp": int(time.time() * 1000),
        }

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Truncate order lot size to exchange step precision without rounding up."""
        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f"Invalid lot amount: {amount}")
        norm = self.normalize_symbol(symbol)
        decimals = self._precision_map.get(norm, 4)
        quantizer = Decimal("10") ** (-decimals)
        d_val = Decimal(str(amount)).quantize(quantizer, rounding=ROUND_DOWN)
        return f"{d_val:.{decimals}f}"


class AlternativeMeFearGreedFeed:
    """Fetches Crypto Fear & Greed Index from Alternative.me with deterministic fallback."""

    ENDPOINT = "https://api.alternative.me/fng/?limit=1"

    def __init__(self, offline_mode: bool = True, timeout_sec: float = 5.0):
        self.offline_mode = offline_mode
        self.timeout_sec = timeout_sec

    @staticmethod
    def classify_value(val: int) -> str:
        if val < 0 or val > 100:
            raise ValueError("Fear & Greed index must be between 0 and 100")
        if val <= 24:
            return "Extreme Fear"
        if val <= 49:
            return "Fear"
        if val == 50:
            return "Neutral"
        if val <= 74:
            return "Greed"
        return "Extreme Greed"

    def fetch_fear_and_greed(self, override_value: Optional[int] = None) -> Dict[str, Any]:
        """Fetch latest Fear & Greed index payload."""
        if override_value is not None:
            classification = self.classify_value(override_value)
            return {
                "name": "Crypto Fear & Greed Index",
                "data": [
                    {
                        "value": str(override_value),
                        "value_classification": classification,
                        "timestamp": str(int(time.time())),
                    }
                ],
            }

        if not self.offline_mode:
            try:
                resp = requests.get(self.ENDPOINT, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    payload = resp.json()
                    if "data" in payload and payload["data"]:
                        return payload
            except Exception:
                pass

        default_val = 68
        return {
            "name": "Crypto Fear & Greed Index",
            "data": [
                {
                    "value": str(default_val),
                    "value_classification": self.classify_value(default_val),
                    "timestamp": "1730900000",
                }
            ],
        }


class DeFiLlamaTVLFeed:
    """Fetches chain-level Total Value Locked (TVL) from DeFiLlama REST API."""

    ENDPOINT = "https://api.llama.fi/v2/chains"

    DEFAULT_CHAINS: List[Dict[str, Any]] = [
        {"name": "Ethereum", "tvl": 64500000000.0, "tokenSymbol": "ETH", "chainId": 1},
        {"name": "Solana", "tvl": 8420000000.0, "tokenSymbol": "SOL", "chainId": None},
        {"name": "Bitcoin", "tvl": 3850000000.0, "tokenSymbol": "BTC", "chainId": None},
        {"name": "Arbitrum", "tvl": 3250000000.0, "tokenSymbol": "ARB", "chainId": 42161},
        {"name": "Base", "tvl": 2890000000.0, "tokenSymbol": "ETH", "chainId": 8453},
    ]

    def __init__(self, offline_mode: bool = True, timeout_sec: float = 5.0):
        self.offline_mode = offline_mode
        self.timeout_sec = timeout_sec

    def fetch_chains_tvl(self) -> List[Dict[str, Any]]:
        """Return list of chain TVL records."""
        if not self.offline_mode:
            try:
                resp = requests.get(self.ENDPOINT, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        return data
            except Exception:
                pass
        return [dict(c) for c in self.DEFAULT_CHAINS]

    def get_chain_tvl_map(self) -> Dict[str, float]:
        """Return mapping of chain name -> TVL in USD."""
        chains = self.fetch_chains_tvl()
        return {str(c.get("name")): float(c.get("tvl", 0.0)) for c in chains if c.get("name")}
