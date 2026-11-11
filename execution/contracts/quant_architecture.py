"""
Arbitrum Quantitative Strategy Interface Contracts (Pydantic V2) & Token/Pool Registry.
Implements the canonical Milestone 8 (M-Quant) schemas and verified Arbitrum One addresses.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


CANONICAL_ARBITRUM_SWAP_ROUTER_02 = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
CANONICAL_ARBITRUM_QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
CANONICAL_ARBITRUM_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"


@dataclass(frozen=True)
class TokenSpec:
    symbol: str
    address: str
    decimals: int
    tier: Literal["CORE", "SATELLITE", "STABLE"]
    max_concentration_pct: float
    chandelier_atr_mult: float
    hard_stop_pct: float


ARBITRUM_TOKENS: Dict[str, TokenSpec] = {
    "WBTC": TokenSpec(
        symbol="WBTC",
        address="0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
        decimals=8,
        tier="CORE",
        max_concentration_pct=0.40,
        chandelier_atr_mult=3.0,
        hard_stop_pct=0.05,
    ),
    "WETH": TokenSpec(
        symbol="WETH",
        address="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        decimals=18,
        tier="CORE",
        max_concentration_pct=0.35,
        chandelier_atr_mult=3.0,
        hard_stop_pct=0.05,
    ),
    "ARB": TokenSpec(
        symbol="ARB",
        address="0x912CE59144191C1204E64559FE8253a0e49E6548",
        decimals=18,
        tier="SATELLITE",
        max_concentration_pct=0.20,
        chandelier_atr_mult=2.5,
        hard_stop_pct=0.075,
    ),
    "LINK": TokenSpec(
        symbol="LINK",
        address="0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",
        decimals=18,
        tier="SATELLITE",
        max_concentration_pct=0.20,
        chandelier_atr_mult=2.5,
        hard_stop_pct=0.075,
    ),
    "USDC": TokenSpec(
        symbol="USDC",
        address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        decimals=6,
        tier="STABLE",
        max_concentration_pct=1.00,
        chandelier_atr_mult=0.0,
        hard_stop_pct=0.0,
    ),
}

# Verified primary Uniswap v3 pool fee tiers (in hundredths of a bip) on Arbitrum One
ARBITRUM_POOLS: Dict[Tuple[str, str], int] = {
    ("WBTC", "WETH"): 500,
    ("WETH", "WBTC"): 500,
    ("WETH", "USDC"): 500,
    ("USDC", "WETH"): 500,
    ("WBTC", "USDC"): 500,
    ("USDC", "WBTC"): 500,
    ("ARB", "WETH"): 500,
    ("WETH", "ARB"): 500,
    ("LINK", "WETH"): 3000,
    ("WETH", "LINK"): 3000,
    ("ARB", "USDC"): 3000,
    ("USDC", "ARB"): 3000,
}


class MacroRegime(str, Enum):
    RISK_ON = "RISK_ON"              # M_t >= 0.70: Bull trend, low vol, positive sentiment
    NEUTRAL = "NEUTRAL"              # 0.30 <= M_t < 0.70: Choppy / consolidation
    RISK_OFF = "RISK_OFF"            # M_t < 0.30: Bear trend or volatility shock
    PANIC_DE_RISK = "PANIC_DE_RISK"  # Drawdown breaker tripped or flash crash


class CircuitBreakerStatus(str, Enum):
    NORMAL = "NORMAL"
    TIER1_CAUTION = "TIER1_CAUTION"          # Daily DD >= 3% or Cum DD >= 8%
    TIER2_DAILY_LOCK = "TIER2_DAILY_LOCK"    # Daily DD >= 5%
    TIER3_LOCKED_DOWN = "TIER3_LOCKED_DOWN"  # Cum DD >= 15% (Emergency Flight to USDC)


class TokenMarketData(BaseModel):
    token_address: str
    symbol: str
    price_usd: float
    atr_14: float
    normalized_atr_pct: float
    volume_24h_usd: float = 0.0
    fee_tier: int = 500


class MarketRegimeState(BaseModel):
    timestamp: datetime
    chain_id: int = 42161
    regime: MacroRegime
    macro_score: float = Field(ge=0.0, le=1.0)
    btc_sma50_above_200: bool
    btc_above_sma200: bool = True
    btc_realized_vol_pct: float
    fear_and_greed: int
    confidence: float = Field(ge=0.0, le=1.0)
    tokens: Dict[str, TokenMarketData] = Field(default_factory=dict)


class AlphaSignal(BaseModel):
    pair_or_asset: str
    signal_type: Literal["RATIO_MOMENTUM", "ALTCOIN_ROTATION", "DEFENSIVE_DERISK"]
    raw_score: float
    z_score: float = 0.0
    target_weight: float = Field(ge=0.0, le=1.0)
    time_horizon: str = "4h"
    look_ahead_shift_verified: bool = True


class RebalanceOrder(BaseModel):
    token_in: str
    token_out: str
    symbol_in: str
    symbol_out: str
    amount_in_wei: int
    amount_out_min_wei: int
    fee_tier: int
    fee_tiers_path: List[int] = Field(default_factory=list)
    route_path: List[str]
    route_symbols: List[str] = Field(default_factory=list)
    trade_notional_usd: float = 0.0
    estimated_slippage_bps: float = 0.0
    estimated_gas_usd: float = 0.0
    is_emergency_flight: bool = False


class PortfolioAllocationDecision(BaseModel):
    timestamp: datetime
    macro_regime: MacroRegime
    circuit_breaker_status: CircuitBreakerStatus
    target_weights: Dict[str, float]
    risk_budget_pct: float
    rebalance_required: bool
    rationale: str = ""
    orders: List[RebalanceOrder] = Field(default_factory=list)

    @field_validator("target_weights")
    @classmethod
    def validate_weights(cls, weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Target weights must sum to 1.0 (got {total:.4f})")
        return weights


class PreBroadcastCheckResult(BaseModel):
    approved: bool
    layer_passed: Dict[str, bool]
    rejection_reason: Optional[str] = None
    simulated_gas: int = 0
    price_impact_pct: float = 0.0
