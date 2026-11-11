"""
Unit & Strategy Verification Suite for Milestone 8 (M-Quant Cross-Asset Strategy).
Tests mathematical invariants, risk caps, circuit breakers, Chandelier stops, and multi-hop V3 routing.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from crypto_pipeline.strategies.quant_rotation import (
    MQuantRotationStrategy,
    MacroRegimeAndAltcoinEngine,
    RatioMomentumEngine,
    RiskAndDriftAllocator,
)
from execution.contracts.quant_architecture import (
    ARBITRUM_TOKENS,
    CANONICAL_ARBITRUM_QUOTER_V2,
    CircuitBreakerStatus,
    MacroRegime,
    MarketRegimeState,
    TokenMarketData,
)
from execution.routers.dex_router import MultiDEXRouter


def _sample_market_snapshot() -> dict[str, TokenMarketData]:
    return {
        "WBTC": TokenMarketData(
            token_address=ARBITRUM_TOKENS["WBTC"].address,
            symbol="WBTC",
            price_usd=88500.0,
            atr_14=2212.5,
            normalized_atr_pct=0.025,
            volume_24h_usd=5e8,
        ),
        "WETH": TokenMarketData(
            token_address=ARBITRUM_TOKENS["WETH"].address,
            symbol="WETH",
            price_usd=3120.0,
            atr_14=109.2,
            normalized_atr_pct=0.035,
            volume_24h_usd=4e8,
        ),
        "ARB": TokenMarketData(
            token_address=ARBITRUM_TOKENS["ARB"].address,
            symbol="ARB",
            price_usd=0.70,
            atr_14=0.0546,
            normalized_atr_pct=0.078,
            volume_24h_usd=5e7,
        ),
        "LINK": TokenMarketData(
            token_address=ARBITRUM_TOKENS["LINK"].address,
            symbol="LINK",
            price_usd=18.0,
            atr_14=1.17,
            normalized_atr_pct=0.065,
            volume_24h_usd=8e7,
        ),
        "USDC": TokenMarketData(
            token_address=ARBITRUM_TOKENS["USDC"].address,
            symbol="USDC",
            price_usd=1.0,
            atr_14=0.0,
            normalized_atr_pct=0.0,
            volume_24h_usd=1e9,
        ),
    }


def test_log_ratio_symmetry():
    wbtc = [80000.0, 82000.0, 85000.0, 88000.0]
    weth = [3000.0, 3050.0, 3100.0, 3200.0]
    r_be = RatioMomentumEngine.compute_log_ratio(wbtc, weth)
    r_eb = RatioMomentumEngine.compute_log_ratio(weth, wbtc)
    assert np.allclose(r_be, -r_eb, atol=1e-12)


def test_z_score_overextension_dampening():
    rmo = RatioMomentumEngine(z_entry=1.50, z_cap=2.25)
    assert rmo.overextension_dampener(0.8) == pytest.approx(1.0)
    assert rmo.overextension_dampener(-1.50) == pytest.approx(1.0)
    mid = rmo.overextension_dampener(1.875)
    assert mid == pytest.approx(0.5)
    assert rmo.overextension_dampener(2.26) == pytest.approx(0.0)
    assert rmo.overextension_dampener(-3.5) == pytest.approx(0.0)


def test_core_bounds_wbtc_weth():
    rmo = RatioMomentumEngine()
    # Strong steady WBTC outperformance
    wbtc = [80000.0 * (1.003 ** i) for i in range(200)]
    weth = [3000.0 for _ in range(200)]
    w_b, w_e, sig = rmo.evaluate_core_weights(wbtc, weth)
    assert 0.20 <= w_b <= 0.80
    assert 0.20 <= w_e <= 0.80
    assert abs((w_b + w_e) - 1.0) < 1e-9
    assert sig.look_ahead_shift_verified is True


def test_macro_regime_gating_altcoins():
    snap = _sample_market_snapshot()
    # Downtrend BTC -> RISK_OFF (M_t = 0.0 -> altcoins clamped to 0%)
    btc_bear = [95000.0 - i * 150.0 for i in range(210)]
    macro_off = MacroRegimeAndAltcoinEngine.evaluate_macro_regime(btc_bear, fear_and_greed=65, token_snapshot=snap)
    assert macro_off.regime == MacroRegime.RISK_OFF
    assert macro_off.macro_score == 0.0

    macro_engine = MacroRegimeAndAltcoinEngine()
    alt_weights, _ = macro_engine.evaluate_satellite_allocations(
        {"ARB": [1.0 + i * 0.02 for i in range(90)], "LINK": [15.0 + i * 0.2 for i in range(90)]},
        [3000.0] * 90,
        macro_off,
    )
    assert alt_weights == {"ARB": 0.0, "LINK": 0.0}

    # Uptrend BTC with controlled volatility & greed >= 50 -> RISK_ON
    btc_bull = [60000.0 + i * 150.0 for i in range(210)]
    macro_on = MacroRegimeAndAltcoinEngine.evaluate_macro_regime(btc_bull, fear_and_greed=72, token_snapshot=snap)
    assert macro_on.regime == MacroRegime.RISK_ON
    assert macro_on.macro_score >= 0.70


def test_inverse_vol_weights():
    snap = _sample_market_snapshot()
    weights = RiskAndDriftAllocator.compute_inverse_volatility_weights(
        ["WBTC", "WETH", "LINK", "ARB"], snap, risk_budget=0.80
    )
    assert weights["WBTC"] > weights["WETH"] > weights["LINK"] > weights["ARB"]
    assert abs(sum(weights.values()) - 0.80) < 1e-9


def test_concentration_clamping():
    weights = RiskAndDriftAllocator.project_concentration_limits(
        core_wbtc_share=0.80,
        core_weth_share=0.20,
        satellite_weights={"ARB": 0.35, "LINK": 0.35},
        risk_budget=0.90,
    )
    assert weights["WBTC"] <= 0.40
    assert weights["WETH"] <= 0.35
    assert weights["WBTC"] + weights["WETH"] <= 0.75
    assert weights["ARB"] <= 0.20
    assert weights["LINK"] <= 0.20
    assert weights["ARB"] + weights["LINK"] <= 0.30
    assert weights["USDC"] >= 0.10
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_chandelier_stop_ratchet():
    stop1 = RiskAndDriftAllocator.update_chandelier_stop(
        highs_window=[3000.0, 3100.0, 3200.0],
        atr14=100.0,
        prev_stop=0.0,
        atr_mult=3.0,
        entry_price=3050.0,
        hard_stop_pct=0.05,
    )
    # Candidate = 3200 - 300 = 2900; floor = 3050 * 0.95 = 2897.5 -> 2900
    assert stop1 == pytest.approx(2900.0)

    # Even if highs dip, stop NEVER loosens
    stop2 = RiskAndDriftAllocator.update_chandelier_stop(
        highs_window=[2950.0, 2960.0],
        atr14=120.0,
        prev_stop=stop1,
        atr_mult=3.0,
    )
    assert stop2 == stop1


def test_circuit_breakers_tiers_1_2_3_and_flight_sequence():
    assert RiskAndDriftAllocator.evaluate_circuit_breaker(1.0, 2.0) == CircuitBreakerStatus.NORMAL
    assert RiskAndDriftAllocator.evaluate_circuit_breaker(3.5, 4.0) == CircuitBreakerStatus.TIER1_CAUTION
    assert RiskAndDriftAllocator.evaluate_circuit_breaker(5.2, 6.0) == CircuitBreakerStatus.TIER2_DAILY_LOCK
    assert RiskAndDriftAllocator.evaluate_circuit_breaker(2.0, 15.5) == CircuitBreakerStatus.TIER3_LOCKED_DOWN

    snap = _sample_market_snapshot()
    alloc = RiskAndDriftAllocator(min_trade_usd=50.0, max_trade_usd=250.0)
    units = {"WBTC": 0.01, "WETH": 0.2, "ARB": 150.0, "LINK": 10.0, "USDC": 100.0}
    req, orders = alloc.plan_rebalance_orders(
        current_units=units,
        target_weights={"WBTC": 0.0, "WETH": 0.0, "ARB": 0.0, "LINK": 0.0, "USDC": 1.0},
        token_snapshot=snap,
        recipient_address="0x1111111111111111111111111111111111111111",
        circuit_status=CircuitBreakerStatus.TIER3_LOCKED_DOWN,
    )
    assert req is True
    assert [o.symbol_in for o in orders] == ["ARB", "LINK", "WETH", "WBTC"]
    assert all(o.is_emergency_flight for o in orders)
    assert orders[1].route_symbols == ["LINK", "WETH", "USDC"]


def test_dust_and_chunking():
    snap = _sample_market_snapshot()
    alloc = RiskAndDriftAllocator(min_trade_usd=50.0, max_trade_usd=250.0)
    # $1000 USDC portfolio, target 40% WBTC ($400), 35% WETH ($350), 25% USDC
    # $400 > $250 chunk cap -> sliced into $250 + $150; $350 -> sliced into $250 + $100
    units = {"WBTC": 0.0, "WETH": 0.0, "ARB": 0.0, "LINK": 0.0, "USDC": 1000.0}
    targets = {"WBTC": 0.40, "WETH": 0.35, "ARB": 0.0, "LINK": 0.0, "USDC": 0.25}
    req, orders = alloc.plan_rebalance_orders(
        current_units=units,
        target_weights=targets,
        token_snapshot=snap,
        recipient_address="0x1111111111111111111111111111111111111111",
        circuit_status=CircuitBreakerStatus.NORMAL,
    )
    assert req is True
    assert all(50.0 <= o.trade_notional_usd <= 250.0 for o in orders)

    # Tiny portfolio ($40 total) below $50 dust limit -> zero orders emitted
    tiny_units = {"WBTC": 0.0, "WETH": 0.0, "ARB": 0.0, "LINK": 0.0, "USDC": 40.0}
    req_tiny, orders_tiny = alloc.plan_rebalance_orders(
        current_units=tiny_units,
        target_weights=targets,
        token_snapshot=snap,
        recipient_address="0x1111111111111111111111111111111111111111",
        circuit_status=CircuitBreakerStatus.NORMAL,
    )
    assert req_tiny is False
    assert orders_tiny == []


def test_multihop_v3_path_encoding_and_canonical_quoter():
    router = MultiDEXRouter()
    assert router.get_quoter_v2_address(42161) == CANONICAL_ARBITRUM_QUOTER_V2

    syms, addrs, fees = router.resolve_arbitrum_route("LINK", "USDC", trade_notional_usd=1000.0)
    assert syms == ["LINK", "WETH", "USDC"]
    assert fees == [3000, 500]
    packed = router.encode_v3_path(addrs, fees)
    # 20 + 3 + 20 + 3 + 20 = 66 bytes
    assert len(packed) == 66


def test_macro_kelly_risk_budget_scaling_and_negative_edge_halt():
    lam_off, bud_off = RiskAndDriftAllocator.compute_fractional_kelly_budget(
        win_rate=0.58, payoff_ratio=1.65, macro_score=0.10
    )
    lam_on, bud_on = RiskAndDriftAllocator.compute_fractional_kelly_budget(
        win_rate=0.58, payoff_ratio=1.65, macro_score=0.85
    )
    assert lam_on <= 0.35
    assert bud_off < 0.30
    assert 0.70 <= bud_on <= 0.90

    # Negative edge must force 0 risk budget
    _, bud_neg = RiskAndDriftAllocator.compute_fractional_kelly_budget(
        win_rate=0.30, payoff_ratio=1.0, macro_score=0.90
    )
    assert bud_neg == 0.0

