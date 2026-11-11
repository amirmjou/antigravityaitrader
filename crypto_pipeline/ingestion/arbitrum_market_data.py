"""
Live Multi-Asset Market Data & On-Chain QuoterV2 Ingestion for Arbitrum M-Quant Rotation.
Fetches closed OHLCV candles (4h and 1d) for BTC, ETH, ARB, LINK and Alternative.me Fear & Greed,
plus canonical Arbitrum One QuoterV2 pricing & slippage simulation.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from web3 import Web3

from execution.contracts.quant_architecture import (
    ARBITRUM_TOKENS,
    CANONICAL_ARBITRUM_QUOTER_V2,
    TokenMarketData,
)
from execution.routers.dex_router import MultiDEXRouter

logger = logging.getLogger("arbitrum-market-data")

BINANCE_SYMBOLS = {
    "WBTC": "BTCUSDT",
    "WETH": "ETHUSDT",
    "ARB": "ARBUSDT",
    "LINK": "LINKUSDT",
}

COINBASE_PAIRS = {
    "WBTC": "BTC-USD",
    "WETH": "ETH-USD",
    "ARB": "ARB-USD",
    "LINK": "LINK-USD",
}

QUOTER_V2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "path", "type": "bytes"},
            {"name": "amountIn", "type": "uint256"},
        ],
        "name": "quoteExactInput",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96AfterList", "type": "uint160[]"},
            {"name": "initializedTicksCrossedList", "type": "uint32[]"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def _http_get_json(url: str, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "AntigravityQuant/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_closed_klines(
    symbol: str,
    interval: str = "4h",
    limit: int = 220,
) -> List[List[float]]:
    """
    Fetch historical closed OHLCV bars: [ts_ms, open, high, low, close, volume].
    Drops the still-forming latest candle so all indicators consume strictly closed bars (t-1).
    Falls back to Coinbase spot-anchored synthetic sequence only if all public APIs fail.
    """
    sym_u = symbol.upper()
    pair = BINANCE_SYMBOLS.get(sym_u, f"{sym_u}USDT")

    # Try Binance public data-api first (fast global CDN, zero timeout on geo-restricted regions)
    for host in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            url = f"{host}/api/v3/klines?symbol={pair}&interval={interval}&limit={limit + 1}"
            raw = _http_get_json(url, timeout=4.0)
            if isinstance(raw, list) and len(raw) >= 30:
                # Drop last candle (currently open bar) to eliminate look-ahead bias
                closed = raw[:-1]
                return [
                    [float(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])]
                    for c in closed[-limit:]
                ]
        except Exception:
            continue

    # Try Coinbase Exchange public candles API
    try:
        cb_pair = COINBASE_PAIRS.get(sym_u, "ETH-USD")
        granularity = 86400 if interval == "1d" else 3600
        url = f"https://api.exchange.coinbase.com/products/{cb_pair}/candles?granularity={granularity}"
        raw = _http_get_json(url, timeout=8.0)
        if isinstance(raw, list) and len(raw) >= 30:
            # Coinbase returns newest first: [time, low, high, open, close, volume]
            ordered = list(reversed(raw[1 : limit + 1]))
            return [
                [float(c[0]) * 1000.0, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])]
                for c in ordered
            ]
    except Exception:
        pass

    # Fallback: spot quote from Coinbase v2
    spot = fetch_live_spot_price(sym_u)
    return [[float(i * 14400000), spot, spot * 1.005, spot * 0.995, spot, 1000.0] for i in range(limit)]


def fetch_live_spot_price(symbol: str) -> float:
    """Fetch current spot USD price via Coinbase / Binance public endpoints."""
    sym_u = symbol.upper()
    if sym_u == "USDC":
        return 1.0

    cb_pair = COINBASE_PAIRS.get(sym_u)
    if cb_pair:
        try:
            data = _http_get_json(f"https://api.coinbase.com/v2/prices/{cb_pair}/spot", timeout=5.0)
            return float(data["data"]["amount"])
        except Exception:
            pass

    bn_pair = BINANCE_SYMBOLS.get(sym_u)
    if bn_pair:
        try:
            data = _http_get_json(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={bn_pair}", timeout=5.0)
            return float(data["price"])
        except Exception:
            pass

    defaults = {"WBTC": 88500.0, "WETH": 3120.0, "ARB": 0.65, "LINK": 18.0}
    return defaults.get(sym_u, 1.0)


def fetch_fear_and_greed_index() -> int:
    """Fetch latest closed Fear & Greed Index (0-100) from Alternative.me with safe fallback."""
    try:
        data = _http_get_json("https://api.alternative.me/fng/?limit=2", timeout=5.0)
        entries = data.get("data", [])
        if entries:
            return int(entries[0]["value"])
    except Exception:
        pass
    return 50


def compute_atr14(candles: List[List[float]]) -> float:
    """Compute 14-period Average True Range from [ts, open, high, low, close, vol]."""
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    start = max(1, len(candles) - 14)
    for i in range(start, len(candles)):
        h, l, prev_c = candles[i][2], candles[i][3], candles[i - 1][4]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return float(np.mean(trs)) if trs else 0.0


def build_token_market_snapshot(daily_candles: Dict[str, List[List[float]]]) -> Dict[str, TokenMarketData]:
    """Construct TokenMarketData map for all universe tokens."""
    snapshot: Dict[str, TokenMarketData] = {}
    for sym, spec in ARBITRUM_TOKENS.items():
        if sym == "USDC":
            snapshot[sym] = TokenMarketData(
                token_address=spec.address,
                symbol="USDC",
                price_usd=1.0,
                atr_14=0.0,
                normalized_atr_pct=0.0,
                volume_24h_usd=1e9,
                fee_tier=500,
            )
            continue

        candles = daily_candles.get(sym, [])
        if candles:
            last_close = float(candles[-1][4])
            atr14 = compute_atr14(candles)
            norm_atr = (atr14 / last_close) if last_close > 0 else 0.03
        else:
            last_close = fetch_live_spot_price(sym)
            atr14 = last_close * 0.03
            norm_atr = 0.03

        snapshot[sym] = TokenMarketData(
            token_address=spec.address,
            symbol=sym,
            price_usd=last_close,
            atr_14=atr14,
            normalized_atr_pct=norm_atr,
            volume_24h_usd=float(candles[-1][5] * last_close) if candles else 0.0,
            fee_tier=3000 if sym == "LINK" else 500,
        )
    return snapshot


def quote_uniswap_v3_swap(
    w3: Web3,
    route_addresses: List[str],
    fee_tiers: List[int],
    amount_in_wei: int,
    quoter_address: str = CANONICAL_ARBITRUM_QUOTER_V2,
) -> Tuple[int, int]:
    """
    Query Arbitrum One QuoterV2 via eth_call for single-hop or multi-hop exactInput.
    Returns (expected_amount_out_wei, gas_estimate). Raises on revert.
    """
    quoter = w3.eth.contract(address=Web3.to_checksum_address(quoter_address), abi=QUOTER_V2_ABI)
    if len(route_addresses) == 2:
        params = (
            Web3.to_checksum_address(route_addresses[0]),
            Web3.to_checksum_address(route_addresses[1]),
            int(amount_in_wei),
            int(fee_tiers[0]),
            0,
        )
        res = quoter.functions.quoteExactInputSingle(params).call()
        return int(res[0]), int(res[3])
    else:
        path_bytes = MultiDEXRouter.encode_v3_path(route_addresses, fee_tiers)
        res = quoter.functions.quoteExactInput(path_bytes, int(amount_in_wei)).call()
        return int(res[0]), int(res[3])
