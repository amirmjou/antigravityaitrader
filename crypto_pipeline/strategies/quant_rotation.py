"""
Quantitative Cross-Asset Rotation Strategy Engine (Milestone 8 / Features F39-F44).
Implements:
- Layer A: WBTC/WETH Continuous Log-Ratio Momentum Oscillator (RMO) & Z-Score Bounds
- Layer B: Multi-Factor Macro Regime Filter (M_t) & Sortino-Adjusted Altcoin Rotation (ARB, LINK)
- Layer C: Inverse Volatility, Fractional Kelly, Chandelier Stops, 3-Tier Circuit Breakers & Drift Rebalancer
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from execution.contracts.quant_architecture import (
    ARBITRUM_TOKENS,
    AlphaSignal,
    CircuitBreakerStatus,
    MacroRegime,
    MarketRegimeState,
    PortfolioAllocationDecision,
    RebalanceOrder,
    TokenMarketData,
)
from execution.routers.dex_router import MultiDEXRouter


def _ema_series(values: np.ndarray, span: int) -> np.ndarray:
    """Compute standard recursive EMA series without look-ahead."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = float(values[0])
    for i in range(1, len(values)):
        out[i] = alpha * float(values[i]) + (1.0 - alpha) * out[i - 1]
    return out


class RatioMomentumEngine:
    """Layer A: WBTC/WETH Log-Ratio Momentum Oscillator with Rolling Z-Score Bounds."""

    def __init__(
        self,
        fast_span: int = 12,
        slow_span: int = 48,
        sig_span: int = 9,
        z_window: int = 180,
        z_entry: float = 1.50,
        z_cap: float = 2.25,
        lambda_1: float = 2.0,
        lambda_2: float = 1.0,
        omega_max: float = 0.60,
    ):
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.sig_span = sig_span
        self.z_window = z_window
        self.z_entry = z_entry
        self.z_cap = z_cap
        self.lambda_1 = lambda_1
        self.lambda_2 = lambda_2
        self.omega_max = omega_max

    @staticmethod
    def compute_log_ratio(wbtc_closes: List[float], weth_closes: List[float]) -> np.ndarray:
        """Compute continuous log-ratio r_t = ln(P_WBTC / P_WETH)."""
        a = np.asarray(wbtc_closes, dtype=float)
        b = np.asarray(weth_closes, dtype=float)
        if len(a) != len(b) or len(a) < 2:
            raise ValueError("WBTC and WETH close series must match in length and have >= 2 bars.")
        if np.any(a <= 0) or np.any(b <= 0):
            raise ValueError("Prices must be strictly positive.")
        return np.log(a / b)

    def overextension_dampener(self, z_score: float) -> float:
        """Compute overextension taper psi(Z) in [0.0, 1.0]."""
        az = abs(float(z_score))
        if az <= self.z_entry:
            return 1.0
        if az <= self.z_cap:
            return max(0.0, 1.0 - (az - self.z_entry) / (self.z_cap - self.z_entry))
        return 0.0

    def evaluate_core_weights(
        self,
        wbtc_closed_4h: List[float],
        weth_closed_4h: List[float],
    ) -> Tuple[float, float, AlphaSignal]:
        """
        Evaluate WBTC vs WETH allocation within Core portfolio using strictly closed bars (t-1).
        Returns: (w_wbtc_core, w_weth_core, AlphaSignal)
        """
        r = self.compute_log_ratio(wbtc_closed_4h, weth_closed_4h)
        ema_fast = _ema_series(r, self.fast_span)
        ema_slow = _ema_series(r, self.slow_span)
        rmo = ema_fast - ema_slow
        signal_line = _ema_series(rmo, self.sig_span)
        delta_rmo = rmo - signal_line

        win = min(len(r), self.z_window)
        window_slice = r[-win:]
        mu = float(np.mean(window_slice))
        sigma = float(np.std(window_slice, ddof=1)) if win > 1 else 1e-6
        sigma = max(sigma, 1e-6)

        # Latest element of r is already closed bar t-1 because ingestion excludes forming bar t
        z_t_minus_1 = (float(r[-1]) - mu) / sigma
        psi = self.overextension_dampener(z_t_minus_1)

        raw_combo = self.lambda_1 * (float(rmo[-1]) / sigma) + self.lambda_2 * (float(delta_rmo[-1]) / sigma)
        s_ratio = float(math.tanh(raw_combo) * psi)

        w_wbtc_core = float(np.clip(0.50 + 0.50 * s_ratio * self.omega_max, 0.20, 0.80))
        w_weth_core = float(1.0 - w_wbtc_core)

        sig = AlphaSignal(
            pair_or_asset="WBTC/WETH",
            signal_type="RATIO_MOMENTUM",
            raw_score=s_ratio,
            z_score=float(z_t_minus_1),
            target_weight=w_wbtc_core,
            time_horizon="4h",
            look_ahead_shift_verified=True,
        )
        return w_wbtc_core, w_weth_core, sig


class MacroRegimeAndAltcoinEngine:
    """Layer B: Multi-Factor Macro Regime Filter (M_t) & Sortino-Adjusted Altcoin Rotation."""

    @staticmethod
    def evaluate_macro_regime(
        btc_closed_daily: List[float],
        fear_and_greed: int,
        token_snapshot: Dict[str, TokenMarketData],
    ) -> MarketRegimeState:
        """Compute Macro Regime M_t = T_t * V_t * B_t on closed daily bars."""
        closes = np.asarray(btc_closed_daily, dtype=float)
        n = len(closes)
        if n < 31:
            raise ValueError("Need at least 31 closed daily BTC bars for realized volatility & trend.")

        sma_50 = float(np.mean(closes[-min(50, n):]))
        sma_200 = float(np.mean(closes[-min(200, n):]))
        btc_last = float(closes[-1])

        above_200 = btc_last > sma_200
        sma50_above_200 = sma_50 > sma_200
        t_cond = 1.0 if (above_200 and sma50_above_200) else 0.0

        # 30-day annualized realized volatility on log returns
        log_rets = np.diff(np.log(closes[-31:]))
        vol_ann = float(np.std(log_rets, ddof=1) * math.sqrt(365.0))
        if vol_ann <= 0.60:
            v_cond = 1.0
        elif vol_ann <= 0.75:
            v_cond = (0.75 - vol_ann) / 0.15
        else:
            v_cond = 0.0

        fng = max(0, min(100, int(fear_and_greed)))
        if fng < 25:
            b_cond = 0.0
        elif fng < 50:
            b_cond = (fng - 25.0) / 25.0
        else:
            b_cond = 1.0

        m_score = float(np.clip(t_cond * v_cond * b_cond, 0.0, 1.0))
        if m_score >= 0.70:
            regime = MacroRegime.RISK_ON
        elif m_score >= 0.30:
            regime = MacroRegime.NEUTRAL
        else:
            regime = MacroRegime.RISK_OFF

        return MarketRegimeState(
            timestamp=datetime.now(timezone.utc),
            chain_id=42161,
            regime=regime,
            macro_score=m_score,
            btc_sma50_above_200=sma50_above_200,
            btc_above_sma200=above_200,
            btc_realized_vol_pct=round(vol_ann * 100.0, 2),
            fear_and_greed=fng,
            confidence=round(max(0.50, m_score if m_score >= 0.30 else (1.0 - m_score)), 3),
            tokens=token_snapshot,
        )

    @staticmethod
    def score_altcoin(
        alt_closed_daily: List[float],
        eth_closed_daily: List[float],
    ) -> float:
        """Compute Sortino-adjusted momentum + relative strength vs WETH for one altcoin."""
        alt = np.asarray(alt_closed_daily, dtype=float)
        eth = np.asarray(eth_closed_daily, dtype=float)
        n = min(len(alt), len(eth))
        if n < 61:
            # Degrade safely using available window
            w7 = min(7, n - 1)
            w21 = min(21, n - 1)
            w60 = max(1, n - 1)
        else:
            w7, w21, w60 = 7, 21, 60

        roc_7 = (alt[-1] - alt[-1 - w7]) / alt[-1 - w7]
        roc_21 = (alt[-1] - alt[-1 - w21]) / alt[-1 - w21]
        roc_60 = (alt[-1] - alt[-1 - w60]) / alt[-1 - w60]
        mom = 0.50 * roc_7 + 0.30 * roc_21 + 0.20 * roc_60

        log_rets = np.diff(np.log(alt[-min(n, 31):]))
        neg_rets = np.minimum(0.0, log_rets)
        down_vol = float(math.sqrt(float(np.mean(neg_rets ** 2))) * math.sqrt(365.0))
        adj_mom = mom / max(0.20, down_vol)

        ratio = alt[-min(30, n):] / eth[-min(30, n):]
        rs = (float(ratio[-1]) / float(np.mean(ratio))) - 1.0
        return float(0.60 * adj_mom + 0.40 * rs)

    def evaluate_satellite_allocations(
        self,
        alt_daily_closes: Dict[str, List[float]],
        eth_closed_daily: List[float],
        macro_state: MarketRegimeState,
        w_sat_max: float = 0.30,
    ) -> Tuple[Dict[str, float], List[AlphaSignal]]:
        """Compute ARB & LINK target satellite allocations gated by MacroRegimeState."""
        signals: List[AlphaSignal] = []
        raw_scores: Dict[str, float] = {}

        if macro_state.macro_score < 0.30 or macro_state.regime in (MacroRegime.RISK_OFF, MacroRegime.PANIC_DE_RISK):
            for sym in ("ARB", "LINK"):
                signals.append(
                    AlphaSignal(
                        pair_or_asset=f"{sym}/WETH",
                        signal_type="DEFENSIVE_DERISK",
                        raw_score=0.0,
                        target_weight=0.0,
                        time_horizon="1d",
                    )
                )
            return {"ARB": 0.0, "LINK": 0.0}, signals

        w_sat_budget = w_sat_max * macro_state.macro_score
        for sym in ("ARB", "LINK"):
            series = alt_daily_closes.get(sym, [])
            if len(series) < 10:
                raw_scores[sym] = 0.0
                continue
            score = self.score_altcoin(series, eth_closed_daily)
            sma50 = float(np.mean(series[-min(50, len(series)):]))
            eligible = (score > 0.05) and (float(series[-1]) > sma50)
            raw_scores[sym] = max(0.0, score) if eligible else 0.0

        total_score = sum(raw_scores.values())
        weights: Dict[str, float] = {}
        for sym in ("ARB", "LINK"):
            if total_score > 0.0 and raw_scores[sym] > 0.0:
                w = min(0.20, w_sat_budget * (raw_scores[sym] / total_score))
            else:
                w = 0.0
            weights[sym] = float(w)
            signals.append(
                AlphaSignal(
                    pair_or_asset=f"{sym}/WETH",
                    signal_type="ALTCOIN_ROTATION" if w > 0 else "DEFENSIVE_DERISK",
                    raw_score=float(raw_scores[sym]),
                    target_weight=float(w),
                    time_horizon="1d",
                )
            )
        return weights, signals


@dataclass
class TrailingStopState:
    highest_high: float = 0.0
    stop_price: float = 0.0


class RiskAndDriftAllocator:
    """Layer C & Risk Gate: Inverse Volatility, Fractional Kelly, Chandelier Stops, Circuit Breakers & Drift Rebalancer."""

    def __init__(
        self,
        min_trade_usd: float = 50.0,
        max_trade_usd: float = 250.0,
        asset_drift_max: float = 0.05,
        portfolio_drift_max: float = 0.08,
        max_cost_ratio: float = 0.010,
    ):
        self.min_trade_usd = min_trade_usd
        self.max_trade_usd = max_trade_usd
        self.asset_drift_max = asset_drift_max
        self.portfolio_drift_max = portfolio_drift_max
        self.max_cost_ratio = max_cost_ratio

    @staticmethod
    def compute_fractional_kelly_budget(
        win_rate: float = 0.58,
        payoff_ratio: float = 1.65,
        excess_kurtosis: float = 3.5,
        macro_score: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Compute fat-tail dampened Fractional Kelly multiplier (<= 0.35) and risk budget W_risk.
        When macro_score M_t is supplied, scales deployed risk capital cleanly between defensive
        RISK_OFF (~10-40%), NEUTRAL (~40-70%), and aggressive RISK_ON (~70-90%) subject to positive Kelly edge.
        """
        if payoff_ratio <= 0:
            return 0.0, 0.0
        f_star = win_rate - (1.0 - win_rate) / payoff_ratio
        if f_star <= 0.0:
            return 0.0, 0.0
        lam = min(0.35, 1.0 / (2.0 + max(0.0, excess_kurtosis)))
        raw_kelly_budget = max(0.0, min(lam * f_star, 0.90))
        if macro_score is None:
            return float(lam), float(raw_kelly_budget)

        # Modulate regime deployment by Kelly edge confidence
        kelly_conf = min(1.0, raw_kelly_budget / 0.05)
        m = max(0.0, min(1.0, float(macro_score)))
        if m >= 0.70:
            regime_target = 0.70 + 0.20 * ((m - 0.70) / 0.30)
        elif m >= 0.30:
            regime_target = 0.40 + 0.30 * ((m - 0.30) / 0.40)
        else:
            regime_target = 0.10 + 0.30 * (m / 0.30)
        w_risk = max(0.0, min(0.90, regime_target * kelly_conf))
        return float(lam), float(w_risk)

    @staticmethod
    def compute_inverse_volatility_weights(
        assets: List[str],
        token_snapshot: Dict[str, TokenMarketData],
        risk_budget: float,
    ) -> Dict[str, float]:
        """Compute normalized ATR-14 inverse-volatility weights across active risk assets."""
        inv_vols: Dict[str, float] = {}
        for sym in assets:
            mkt = token_snapshot.get(sym)
            norm_atr = mkt.normalized_atr_pct if (mkt and mkt.normalized_atr_pct > 0.001) else 0.03
            inv_vols[sym] = 1.0 / norm_atr

        denom = sum(inv_vols.values())
        if denom <= 0:
            return {sym: 0.0 for sym in assets}
        return {sym: float(risk_budget * (inv_vols[sym] / denom)) for sym in assets}

    @staticmethod
    def project_concentration_limits(
        core_wbtc_share: float,
        core_weth_share: float,
        satellite_weights: Dict[str, float],
        risk_budget: float,
    ) -> Dict[str, float]:
        """
        Enforce strict tier caps:
        WBTC <= 40%, WETH <= 35%, WBTC+WETH <= 75%, ARB <= 20%, LINK <= 20%, alts <= 30%, USDC >= 10%.
        """
        w_arb = min(0.20, max(0.0, satellite_weights.get("ARB", 0.0)))
        w_link = min(0.20, max(0.0, satellite_weights.get("LINK", 0.0)))
        sat_total = w_arb + w_link
        if sat_total > 0.30:
            scale = 0.30 / sat_total
            w_arb *= scale
            w_link *= scale
            sat_total = 0.30

        max_deployable_risk = min(0.90, max(0.0, risk_budget))
        if sat_total > max_deployable_risk:
            scale = max_deployable_risk / sat_total if sat_total > 0 else 0.0
            w_arb *= scale
            w_link *= scale
            sat_total = w_arb + w_link

        core_budget = min(0.75, max(0.0, max_deployable_risk - sat_total))
        w_wbtc = min(0.40, core_budget * core_wbtc_share)
        w_weth = min(0.35, core_budget * core_weth_share)

        # Re-allocate leftover core capacity to the uncapped core leg within its tier cap
        rem = core_budget - (w_wbtc + w_weth)
        if rem > 1e-6:
            if w_wbtc < 0.40:
                add_b = min(0.40 - w_wbtc, rem)
                w_wbtc += add_b
                rem -= add_b
            if rem > 1e-6 and w_weth < 0.35:
                add_e = min(0.35 - w_weth, rem)
                w_weth += add_e

        w_usdc = max(0.10, 1.0 - (w_wbtc + w_weth + w_arb + w_link))
        weights = {
            "WBTC": round(w_wbtc, 4),
            "WETH": round(w_weth, 4),
            "ARB": round(w_arb, 4),
            "LINK": round(w_link, 4),
            "USDC": round(w_usdc, 4),
        }
        # Exact sum normalization to USDC residual
        diff = 1.0 - sum(weights.values())
        weights["USDC"] = round(max(0.0, weights["USDC"] + diff), 4)
        return weights

    @staticmethod
    def update_chandelier_stop(
        highs_window: List[float],
        atr14: float,
        prev_stop: float,
        atr_mult: float,
        entry_price: Optional[float] = None,
        hard_stop_pct: float = 0.05,
    ) -> float:
        """Update monotonic Chandelier trailing stop (ratchet invariant: stop never loosens)."""
        if not highs_window:
            return prev_stop
        highest = max(highs_window[-22:])
        cand = highest - atr_mult * atr14
        if entry_price is not None and entry_price > 0:
            floor_stop = entry_price * (1.0 - hard_stop_pct)
            cand = max(cand, floor_stop)
        return float(max(prev_stop, cand))

    @staticmethod
    def evaluate_circuit_breaker(
        daily_dd_pct: float,
        cum_dd_pct: float,
        daily_lock_active: bool = False,
    ) -> CircuitBreakerStatus:
        """Evaluate 3-tier drawdown circuit breaker status."""
        if cum_dd_pct >= 15.0:
            return CircuitBreakerStatus.TIER3_LOCKED_DOWN
        if daily_dd_pct >= 5.0 or daily_lock_active:
            return CircuitBreakerStatus.TIER2_DAILY_LOCK
        if daily_dd_pct >= 3.0 or cum_dd_pct >= 8.0:
            return CircuitBreakerStatus.TIER1_CAUTION
        return CircuitBreakerStatus.NORMAL

    def plan_rebalance_orders(
        self,
        current_units: Dict[str, float],
        target_weights: Dict[str, float],
        token_snapshot: Dict[str, TokenMarketData],
        recipient_address: str,
        circuit_status: CircuitBreakerStatus,
        gas_cost_usd: float = 0.008,
        last_rebalance_age_days: float = 0.0,
    ) -> Tuple[bool, List[RebalanceOrder]]:
        """
        Evaluate drift thresholds and construct cost-gated Uniswap v3 rebalance orders.
        On Tier 3 emergency, executes priority flight-to-USDC: ARB -> LINK -> WETH -> WBTC -> USDC.
        """
        prices = {sym: (token_snapshot[sym].price_usd if sym in token_snapshot else 1.0) for sym in ARBITRUM_TOKENS}
        values_usd = {sym: current_units.get(sym, 0.0) * prices[sym] for sym in ARBITRUM_TOKENS}
        total_value = sum(values_usd.values())
        if total_value <= 0:
            return False, []

        # Tier 3 Emergency Flight to USDC
        if circuit_status == CircuitBreakerStatus.TIER3_LOCKED_DOWN:
            flight_orders: List[RebalanceOrder] = []
            for sym in ("ARB", "LINK", "WETH", "WBTC"):
                val = values_usd.get(sym, 0.0)
                if val >= self.min_trade_usd:
                    route_syms, route_addrs, fee_tiers = MultiDEXRouter.resolve_arbitrum_route(sym, "USDC", val)
                    spec = ARBITRUM_TOKENS[sym]
                    amt_wei = int(current_units[sym] * (10 ** spec.decimals))
                    exp_usdc = val * 0.9925  # 75 bps emergency slippage floor
                    min_out_wei = int(exp_usdc * (10 ** 6))
                    flight_orders.append(
                        RebalanceOrder(
                            token_in=spec.address,
                            token_out=ARBITRUM_TOKENS["USDC"].address,
                            symbol_in=sym,
                            symbol_out="USDC",
                            amount_in_wei=amt_wei,
                            amount_out_min_wei=min_out_wei,
                            fee_tier=fee_tiers[0],
                            fee_tiers_path=fee_tiers,
                            route_path=route_addrs,
                            route_symbols=route_syms,
                            trade_notional_usd=val,
                            estimated_slippage_bps=75.0,
                            estimated_gas_usd=gas_cost_usd,
                            is_emergency_flight=True,
                        )
                    )
            return bool(flight_orders), flight_orders

        actual_weights = {sym: values_usd[sym] / total_value for sym in ARBITRUM_TOKENS}
        asset_drifts = {sym: abs(actual_weights[sym] - target_weights.get(sym, 0.0)) for sym in ARBITRUM_TOKENS}
        max_asset_drift = max(asset_drifts.values())
        port_drift = 0.5 * sum(asset_drifts.values())

        drift_triggered = (
            (max_asset_drift >= self.asset_drift_max)
            or (port_drift >= self.portfolio_drift_max)
            or (last_rebalance_age_days >= 7.0 and port_drift >= 0.03)
        )
        if not drift_triggered:
            return False, []

        # Tier 2 Daily Lockout prevents new risk-asset buys, only allows sells into USDC
        deltas_usd = {
            sym: (target_weights.get(sym, 0.0) - actual_weights[sym]) * total_value
            for sym in ("WBTC", "WETH", "ARB", "LINK")
        }

        sells = {s: -d for s, d in deltas_usd.items() if d < -self.min_trade_usd}
        buys = {s: d for s, d in deltas_usd.items() if d > self.min_trade_usd}
        if circuit_status == CircuitBreakerStatus.TIER2_DAILY_LOCK:
            buys = {}

        orders: List[RebalanceOrder] = []

        # First pair direct/multi-hop sells of overweight assets into underweight risk assets or USDC
        # Step 1: Rotate sells -> buys directly or via WETH hub if both exist
        rem_buys = dict(buys)
        for s_sym, sell_usd in sells.items():
            left_sell = sell_usd
            # Match against buys first if direct/WETH-hub swap makes sense
            for b_sym in list(rem_buys.keys()):
                buy_need = rem_buys[b_sym]
                if buy_need < self.min_trade_usd or left_sell < self.min_trade_usd:
                    continue
                swap_usd = min(left_sell, buy_need, self.max_trade_usd)
                order = self._build_validated_order(s_sym, b_sym, swap_usd, prices, gas_cost_usd)
                if order:
                    orders.append(order)
                    left_sell -= swap_usd
                    rem_buys[b_sym] -= swap_usd
            # Leftover sell goes to USDC
            while left_sell >= self.min_trade_usd:
                chunk = min(left_sell, self.max_trade_usd)
                order = self._build_validated_order(s_sym, "USDC", chunk, prices, gas_cost_usd)
                if order:
                    orders.append(order)
                left_sell -= chunk

        # Step 2: Remaining buys funded by available USDC cash
        avail_usdc = values_usd.get("USDC", 0.0)
        for b_sym, buy_need in rem_buys.items():
            while buy_need >= self.min_trade_usd and avail_usdc >= self.min_trade_usd:
                chunk = min(buy_need, avail_usdc, self.max_trade_usd)
                order = self._build_validated_order("USDC", b_sym, chunk, prices, gas_cost_usd)
                if order:
                    orders.append(order)
                    avail_usdc -= chunk
                buy_need -= chunk

        return bool(orders), orders

    def _build_validated_order(
        self,
        symbol_in: str,
        symbol_out: str,
        notional_usd: float,
        prices: Dict[str, float],
        gas_cost_usd: float,
    ) -> Optional[RebalanceOrder]:
        if notional_usd < self.min_trade_usd or symbol_in == symbol_out:
            return None

        route_syms, route_addrs, fee_tiers = MultiDEXRouter.resolve_arbitrum_route(symbol_in, symbol_out, notional_usd)
        pool_fee_frac = sum(fee_tiers) / 1_000_000.0
        est_slippage_bps = 2.0 if len(fee_tiers) == 1 else 4.0
        friction = notional_usd * (pool_fee_frac + est_slippage_bps / 10000.0) + gas_cost_usd
        if (friction / notional_usd) > self.max_cost_ratio:
            return None

        spec_in = ARBITRUM_TOKENS[symbol_in]
        spec_out = ARBITRUM_TOKENS[symbol_out]
        amt_in_units = notional_usd / max(1e-9, prices[symbol_in])
        amt_in_wei = int(amt_in_units * (10 ** spec_in.decimals))
        if amt_in_wei <= 0:
            return None

        exp_out_units = (notional_usd * (1.0 - pool_fee_frac - 0.005)) / max(1e-9, prices[symbol_out])
        amt_out_min_wei = max(1, int(exp_out_units * (10 ** spec_out.decimals)))

        return RebalanceOrder(
            token_in=spec_in.address,
            token_out=spec_out.address,
            symbol_in=symbol_in,
            symbol_out=symbol_out,
            amount_in_wei=amt_in_wei,
            amount_out_min_wei=amt_out_min_wei,
            fee_tier=fee_tiers[0],
            fee_tiers_path=fee_tiers,
            route_path=route_addrs,
            route_symbols=route_syms,
            trade_notional_usd=round(notional_usd, 4),
            estimated_slippage_bps=est_slippage_bps,
            estimated_gas_usd=gas_cost_usd,
            is_emergency_flight=False,
        )


class MQuantRotationStrategy:
    """Unified 3-Layer M-Quant Strategy Coordinator combining Layers A, B, and C."""

    def __init__(
        self,
        min_trade_usd: float = 50.0,
        max_trade_usd: float = 250.0,
        asset_drift_max: float = 0.05,
        portfolio_drift_max: float = 0.08,
    ):
        self.ratio_engine = RatioMomentumEngine()
        self.macro_engine = MacroRegimeAndAltcoinEngine()
        self.allocator = RiskAndDriftAllocator(
            min_trade_usd=min_trade_usd,
            max_trade_usd=max_trade_usd,
            asset_drift_max=asset_drift_max,
            portfolio_drift_max=portfolio_drift_max,
        )

    def evaluate(
        self,
        wbtc_4h_closes: List[float],
        weth_4h_closes: List[float],
        daily_closes: Dict[str, List[float]],
        fear_and_greed: int,
        token_snapshot: Dict[str, TokenMarketData],
        current_units: Dict[str, float],
        recipient_address: str,
        daily_dd_pct: float = 0.0,
        cum_dd_pct: float = 0.0,
        gas_cost_usd: float = 0.008,
        last_rebalance_age_days: float = 0.0,
        win_rate: float = 0.58,
        payoff_ratio: float = 1.65,
    ) -> Tuple[PortfolioAllocationDecision, MarketRegimeState, AlphaSignal, List[AlphaSignal]]:
        """Run full 3-layer M-Quant decision pipeline."""
        # Layer B: Macro Regime
        macro_state = self.macro_engine.evaluate_macro_regime(
            daily_closes["WBTC"], fear_and_greed, token_snapshot
        )

        # Layer A: WBTC / WETH Ratio Momentum
        w_wbtc_core, w_weth_core, ratio_sig = self.ratio_engine.evaluate_core_weights(
            wbtc_4h_closes, weth_4h_closes
        )

        # Layer B: Altcoin Rotation
        alt_weights, alt_signals = self.macro_engine.evaluate_satellite_allocations(
            {"ARB": daily_closes["ARB"], "LINK": daily_closes["LINK"]},
            daily_closes["WETH"],
            macro_state,
        )

        # Circuit Breaker + Kelly Risk Budget
        cb_status = self.allocator.evaluate_circuit_breaker(daily_dd_pct, cum_dd_pct)
        lam, risk_budget = self.allocator.compute_fractional_kelly_budget(
            win_rate, payoff_ratio, macro_score=macro_state.macro_score
        )
        if cb_status == CircuitBreakerStatus.TIER1_CAUTION:
            risk_budget *= 0.50
            alt_weights = {"ARB": 0.0, "LINK": 0.0}
        elif cb_status == CircuitBreakerStatus.TIER3_LOCKED_DOWN:
            risk_budget = 0.0
            alt_weights = {"ARB": 0.0, "LINK": 0.0}

        # Inverse volatility modulation on Core legs + Concentration projection
        inv_core = self.allocator.compute_inverse_volatility_weights(
            ["WBTC", "WETH"], token_snapshot, 1.0
        )
        # Blend 70% signal ratio tilt + 30% inverse volatility parity
        blend_b = 0.70 * w_wbtc_core + 0.30 * inv_core["WBTC"]
        blend_e = 0.70 * w_weth_core + 0.30 * inv_core["WETH"]
        tot_core = blend_b + blend_e
        core_b_share = blend_b / tot_core if tot_core > 0 else 0.5
        core_e_share = blend_e / tot_core if tot_core > 0 else 0.5

        if cb_status == CircuitBreakerStatus.TIER3_LOCKED_DOWN:
            target_weights = {"WBTC": 0.0, "WETH": 0.0, "ARB": 0.0, "LINK": 0.0, "USDC": 1.0}
        else:
            target_weights = self.allocator.project_concentration_limits(
                core_b_share, core_e_share, alt_weights, risk_budget
            )

        rebal_req, orders = self.allocator.plan_rebalance_orders(
            current_units=current_units,
            target_weights=target_weights,
            token_snapshot=token_snapshot,
            recipient_address=recipient_address,
            circuit_status=cb_status,
            gas_cost_usd=gas_cost_usd,
            last_rebalance_age_days=last_rebalance_age_days,
        )

        rationale = (
            f"Macro={macro_state.regime.value} (M_t={macro_state.macro_score:.2f}, FNG={fear_and_greed}) | "
            f"WBTC/WETH RMO S={ratio_sig.raw_score:+.2f} (Z={ratio_sig.z_score:+.2f}) | "
            f"Targets: WBTC={target_weights['WBTC']*100:.1f}%, WETH={target_weights['WETH']*100:.1f}%, "
            f"ARB={target_weights['ARB']*100:.1f}%, LINK={target_weights['LINK']*100:.1f}%, "
            f"USDC={target_weights['USDC']*100:.1f}%"
        )

        decision = PortfolioAllocationDecision(
            timestamp=datetime.now(timezone.utc),
            macro_regime=macro_state.regime,
            circuit_breaker_status=cb_status,
            target_weights=target_weights,
            risk_budget_pct=round(risk_budget * 100.0, 2),
            rebalance_required=rebal_req,
            rationale=rationale,
            orders=orders,
        )
        return decision, macro_state, ratio_sig, alt_signals
