"""Quantitative Indicators, Factor/IC Analytics, and Walk-Forward Backtest Engine.

Injects quantitative formulas directly into the Antigravity sandbox execution loop:
- Moving Averages (SMA 20/50/200, EMA 9/12/21/26/50/200, Golden/Death cross detection)
- Wilder's RSI (14-period) with overbought (>70), healthy (30-70), and oversold (<30) regimes
- Wilder's ADX (14-period) with +DI, -DI, DX, ADX trend strength filter (ADX >= 25)
- MACD (12, 26, 9) with histogram and crossover state
- Information Coefficient (Spearman/Pearson IC, IR, t-stat) & Walk-Forward Validation
  (adapted from `skills-for-antigravity/skills/quantitative-research/references/patterns.md`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class MovingAverageSnapshot:
    """Snapshot of SMA and EMA moving averages and trend alignment."""

    price: float
    sma_20: float
    sma_50: float
    sma_200: float
    ema_12: float
    ema_26: float
    ema_50: float
    vs_sma_20_pct: float
    vs_sma_50_pct: float
    vs_sma_200_pct: float
    alignment: str  # "BULLISH_STACK", "BEARISH_STACK", "MIXED"
    golden_cross: bool


@dataclass(frozen=True)
class RSISnapshot:
    """Snapshot of Wilder's Relative Strength Index (RSI)."""

    rsi_14: float
    regime: str  # "OVERBOUGHT" (>70), "OVERSOLD" (<30), "HEALTHY" (30-70)
    signal_bias: str  # "MEAN_REVERT_SHORT", "MEAN_REVERT_LONG", "NEUTRAL_BULLISH", "NEUTRAL_BEARISH"


@dataclass(frozen=True)
class ADXResult:
    """Wilder's Average Directional Index (ADX) and Directional Indicators (+DI, -DI)."""

    adx_14: float
    plus_di: float
    minus_di: float
    dx: float
    is_trending: bool  # True when ADX >= 25.0
    trend_direction: str  # "BULLISH_TREND", "BEARISH_TREND", "RANGING_CHOP"
    filter_passed: bool  # True when ADX filter allows trend-following entries


@dataclass(frozen=True)
class MACDResult:
    """Moving Average Convergence Divergence (12, 26, 9) snapshot."""

    macd_line: float
    signal_line: float
    histogram: float
    state: str  # "BULLISH_CROSS", "BEARISH_CROSS", "BULLISH", "BEARISH"


@dataclass(frozen=True)
class TechnicalSnapshot:
    """Complete technical indicator bundle for `/entry-exit` and `/full-analysis`."""

    ticker: str
    current_price: float
    moving_averages: MovingAverageSnapshot
    rsi: RSISnapshot
    adx: ADXResult
    macd: MACDResult
    atr_14: float
    support_levels: List[float]
    resistance_levels: List[float]
    return_3m_pct: float
    annualized_volatility: float
    regime_label: str  # "bull", "bear", "chop"


@dataclass
class WalkForwardResult:
    """Out-of-sample walk-forward validation result per window."""

    train_sharpe: float
    test_sharpe: float
    train_start: Any
    train_end: Any
    test_start: Any
    test_end: Any
    params: Dict[str, Any] = field(default_factory=dict)
    trades: int = 0


def _to_series(values: Sequence[float] | pd.Series) -> pd.Series:
    if isinstance(values, pd.Series):
        s = values.astype(float).dropna()
    else:
        s = pd.Series(list(values), dtype=float).dropna()
    if len(s) == 0:
        raise ValueError("Input price series cannot be empty.")
    return s


def compute_sma(prices: Sequence[float] | pd.Series, window: int = 20) -> pd.Series:
    """Compute Simple Moving Average (SMA) over `window` periods."""
    if window <= 0:
        raise ValueError("window must be positive")
    s = _to_series(prices)
    return s.rolling(window=window, min_periods=1).mean()


def compute_ema(prices: Sequence[float] | pd.Series, span: int = 20) -> pd.Series:
    """Compute Exponential Moving Average (EMA) over `span` periods."""
    if span <= 0:
        raise ValueError("span must be positive")
    s = _to_series(prices)
    return s.ewm(span=span, adjust=False).mean()


def compute_moving_averages(prices: Sequence[float] | pd.Series) -> MovingAverageSnapshot:
    """Compute SMA(20, 50, 200) and EMA(12, 26, 50) snapshot with alignment regime."""
    s = _to_series(prices)
    current = float(s.iloc[-1])
    sma_20 = float(compute_sma(s, 20).iloc[-1])
    sma_50 = float(compute_sma(s, 50).iloc[-1])
    sma_200 = float(compute_sma(s, 200).iloc[-1])
    ema_12 = float(compute_ema(s, 12).iloc[-1])
    ema_26 = float(compute_ema(s, 26).iloc[-1])
    ema_50 = float(compute_ema(s, 50).iloc[-1])

    vs_20 = ((current - sma_20) / sma_20 * 100.0) if sma_20 > 0 else 0.0
    vs_50 = ((current - sma_50) / sma_50 * 100.0) if sma_50 > 0 else 0.0
    vs_200 = ((current - sma_200) / sma_200 * 100.0) if sma_200 > 0 else 0.0

    if current > sma_20 >= sma_50 >= sma_200:
        alignment = "BULLISH_STACK"
    elif current < sma_20 <= sma_50 <= sma_200:
        alignment = "BEARISH_STACK"
    else:
        alignment = "MIXED"

    return MovingAverageSnapshot(
        price=round(current, 4),
        sma_20=round(sma_20, 4),
        sma_50=round(sma_50, 4),
        sma_200=round(sma_200, 4),
        ema_12=round(ema_12, 4),
        ema_26=round(ema_26, 4),
        ema_50=round(ema_50, 4),
        vs_sma_20_pct=round(vs_20, 2),
        vs_sma_50_pct=round(vs_50, 2),
        vs_sma_200_pct=round(vs_200, 2),
        alignment=alignment,
        golden_cross=bool(sma_50 >= sma_200),
    )


def compute_rsi(prices: Sequence[float] | pd.Series, period: int = 14) -> RSISnapshot:
    """Compute Wilder's RSI (default 14-period) and classify overbought/oversold regime."""
    if period <= 0:
        raise ValueError("period must be positive")
    s = _to_series(prices)
    if len(s) < 2:
        return RSISnapshot(rsi_14=50.0, regime="HEALTHY", signal_bias="NEUTRAL_BULLISH")

    delta = s.diff().dropna()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    avg_gain = gains.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()

    last_gain = float(avg_gain.iloc[-1])
    last_loss = float(avg_loss.iloc[-1])

    if last_loss == 0.0 and last_gain == 0.0:
        rsi_val = 50.0
    elif last_loss == 0.0:
        rsi_val = 100.0
    else:
        rs = last_gain / last_loss
        rsi_val = 100.0 - (100.0 / (1.0 + rs))

    rsi_val = float(np.clip(rsi_val, 0.0, 100.0))
    if rsi_val > 70.0:
        regime = "OVERBOUGHT"
        bias = "MEAN_REVERT_SHORT"
    elif rsi_val < 30.0:
        regime = "OVERSOLD"
        bias = "MEAN_REVERT_LONG"
    else:
        regime = "HEALTHY"
        bias = "NEUTRAL_BULLISH" if rsi_val >= 50.0 else "NEUTRAL_BEARISH"

    return RSISnapshot(
        rsi_14=round(rsi_val, 2),
        regime=regime,
        signal_bias=bias,
    )


def compute_adx(
    high: Sequence[float] | pd.Series,
    low: Sequence[float] | pd.Series,
    close: Sequence[float] | pd.Series,
    period: int = 14,
    adx_threshold: float = 20.0,
) -> ADXResult:
    """Compute Wilder's Average Directional Index (ADX), +DI, -DI, and trend filter."""
    h = _to_series(high).reset_index(drop=True)
    l = _to_series(low).reset_index(drop=True)
    c = _to_series(close).reset_index(drop=True)
    if not (len(h) == len(l) == len(c)):
        raise ValueError("high, low, and close series must have equal length.")
    if len(c) < 3:
        return ADXResult(
            adx_14=15.0,
            plus_di=20.0,
            minus_di=20.0,
            dx=0.0,
            is_trending=False,
            trend_direction="RANGING_CHOP",
            filter_passed=False,
        )

    up_move = h.diff()
    down_move = -l.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0),
        dtype=float,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0),
        dtype=float,
    )

    prev_close = c.shift(1)
    tr1 = (h - l).abs()
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).fillna(tr1)

    atr = tr.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()
    smooth_plus_dm = plus_dm.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()

    safe_atr = atr.replace(0.0, np.nan)
    plus_di_series = (100.0 * smooth_plus_dm / safe_atr).fillna(0.0)
    minus_di_series = (100.0 * smooth_minus_dm / safe_atr).fillna(0.0)

    di_sum = (plus_di_series + minus_di_series).replace(0.0, np.nan)
    dx_series = (100.0 * (plus_di_series - minus_di_series).abs() / di_sum).fillna(0.0)
    adx_series = dx_series.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()

    adx_val = float(np.clip(adx_series.iloc[-1], 0.0, 100.0))
    plus_di_val = float(np.clip(plus_di_series.iloc[-1], 0.0, 100.0))
    minus_di_val = float(np.clip(minus_di_series.iloc[-1], 0.0, 100.0))
    dx_val = float(np.clip(dx_series.iloc[-1], 0.0, 100.0))

    is_trending = adx_val >= 25.0
    filter_passed = adx_val >= adx_threshold
    if filter_passed:
        trend_dir = "BULLISH_TREND" if plus_di_val >= minus_di_val else "BEARISH_TREND"
    else:
        trend_dir = "RANGING_CHOP"

    return ADXResult(
        adx_14=round(adx_val, 2),
        plus_di=round(plus_di_val, 2),
        minus_di=round(minus_di_val, 2),
        dx=round(dx_val, 2),
        is_trending=is_trending,
        trend_direction=trend_dir,
        filter_passed=filter_passed,
    )


def compute_macd(
    prices: Sequence[float] | pd.Series,
    fast_span: int = 12,
    slow_span: int = 26,
    signal_span: int = 9,
) -> MACDResult:
    """Compute MACD (12, 26, 9) line, signal line, histogram, and crossover state."""
    s = _to_series(prices)
    ema_fast = compute_ema(s, fast_span)
    ema_slow = compute_ema(s, slow_span)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_span, adjust=False).mean()
    hist = macd_line - signal_line

    m_now = float(macd_line.iloc[-1])
    sig_now = float(signal_line.iloc[-1])
    h_now = float(hist.iloc[-1])
    h_prev = float(hist.iloc[-2]) if len(hist) >= 2 else h_now

    if h_now > 0 and h_prev <= 0:
        state = "BULLISH_CROSS"
    elif h_now < 0 and h_prev >= 0:
        state = "BEARISH_CROSS"
    elif h_now >= 0:
        state = "BULLISH"
    else:
        state = "BEARISH"

    return MACDResult(
        macd_line=round(m_now, 4),
        signal_line=round(sig_now, 4),
        histogram=round(h_now, 4),
        state=state,
    )


def compute_technical_snapshot(
    ticker: str,
    close: Sequence[float] | pd.Series,
    high: Optional[Sequence[float] | pd.Series] = None,
    low: Optional[Sequence[float] | pd.Series] = None,
) -> TechnicalSnapshot:
    """Compute complete TechnicalSnapshot for `/entry-exit` and `/full-analysis`."""
    c = _to_series(close).reset_index(drop=True)
    h = _to_series(high).reset_index(drop=True) if high is not None else c * 1.012
    l = _to_series(low).reset_index(drop=True) if low is not None else c * 0.988

    ma = compute_moving_averages(c)
    rsi = compute_rsi(c, period=14)
    adx = compute_adx(h, l, c, period=14)
    macd = compute_macd(c)

    prev_c = c.shift(1)
    tr = pd.concat(
        [(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()],
        axis=1,
    ).max(axis=1).fillna((h - l).abs())
    atr_14 = float(tr.rolling(14, min_periods=1).mean().iloc[-1])

    current_price = float(c.iloc[-1])
    lookback_63 = min(len(c) - 1, 63)
    base_price_3m = float(c.iloc[-1 - lookback_63]) if lookback_63 > 0 else current_price
    return_3m_pct = ((current_price - base_price_3m) / base_price_3m * 100.0) if base_price_3m > 0 else 0.0

    rets = c.pct_change().dropna()
    ann_vol = float(rets.tail(20).std() * math.sqrt(252)) if len(rets) >= 2 else 0.25
    avg_vol = float(rets.std() * math.sqrt(252)) if len(rets) >= 10 else ann_vol

    if current_price > ma.sma_50 >= ma.sma_200 and ann_vol <= max(avg_vol * 1.25, 0.45):
        regime = "bull"
    elif current_price < ma.sma_50 < ma.sma_200:
        regime = "bear"
    else:
        regime = "chop"

    recent_window = c.tail(min(len(c), 60))
    swing_low = float(recent_window.quantile(0.15))
    swing_high = float(recent_window.quantile(0.85))
    psych_support = float(math.floor(current_price * 0.95))
    psych_resistance = float(math.ceil(current_price * 1.08))

    supports = sorted(
        {
            round(min(swing_low, current_price * 0.94), 2),
            round(min(ma.sma_50, current_price * 0.96), 2),
            round(max(psych_support, 0.01), 2),
        },
        reverse=True,
    )
    resistances = sorted(
        {
            round(max(swing_high, current_price * 1.05), 2),
            round(max(current_price + 2.5 * atr_14, current_price * 1.12), 2),
            round(max(psych_resistance, current_price * 1.18), 2),
        }
    )

    return TechnicalSnapshot(
        ticker=ticker.upper(),
        current_price=round(current_price, 2),
        moving_averages=ma,
        rsi=rsi,
        adx=adx,
        macd=macd,
        atr_14=round(atr_14, 4),
        support_levels=supports,
        resistance_levels=resistances,
        return_3m_pct=round(return_3m_pct, 2),
        annualized_volatility=round(ann_vol, 4),
        regime_label=regime,
    )


def calculate_information_coefficient(
    signal: pd.Series,
    forward_returns: pd.Series,
    method: str = "spearman",
) -> Dict[str, Any]:
    """Calculate Information Coefficient (IC), IR, and t-statistic between signal and forward returns."""
    aligned = pd.concat([signal, forward_returns], axis=1).dropna()
    if len(aligned) < 5:
        return {
            "ic": 0.0,
            "p_value": 1.0,
            "ic_mean": 0.0,
            "ic_std": 0.0,
            "ir": 0.0,
            "t_stat": 0.0,
            "pct_positive": 0.0,
            "is_significant": False,
        }

    sig_clean = aligned.iloc[:, 0]
    ret_clean = aligned.iloc[:, 1]
    if method == "spearman":
        ic_val, p_val = stats.spearmanr(sig_clean, ret_clean)
    else:
        ic_val, p_val = stats.pearsonr(sig_clean, ret_clean)

    ic_val = 0.0 if np.isnan(ic_val) else float(ic_val)
    p_val = 1.0 if np.isnan(p_val) else float(p_val)

    # Chunk into sub-windows for stability statistics
    n_chunks = max(2, min(12, len(aligned) // 10))
    arr = aligned.to_numpy(dtype=float)
    chunks = np.array_split(arr, n_chunks)
    chunk_ics: List[float] = []
    for chunk in chunks:
        if len(chunk) >= 4:
            c_ic, _ = (
                stats.spearmanr(chunk[:, 0], chunk[:, 1])
                if method == "spearman"
                else stats.pearsonr(chunk[:, 0], chunk[:, 1])
            )
            if not np.isnan(c_ic):
                chunk_ics.append(float(c_ic))

    if not chunk_ics:
        chunk_ics = [ic_val]

    ic_mean = float(np.mean(chunk_ics))
    ic_std = float(np.std(chunk_ics, ddof=1)) if len(chunk_ics) > 1 else 0.05
    safe_std = ic_std if ic_std > 1e-8 else 0.05
    ir = ic_mean / safe_std
    t_stat = ic_mean / (safe_std / math.sqrt(len(chunk_ics)))
    pct_pos = float(np.mean([1.0 if x > 0 else 0.0 for x in chunk_ics]))

    return {
        "ic": round(ic_val, 4),
        "p_value": round(p_val, 6),
        "ic_mean": round(ic_mean, 4),
        "ic_std": round(ic_std, 4),
        "ir": round(ir, 4),
        "t_stat": round(t_stat, 4),
        "pct_positive": round(pct_pos, 4),
        "is_significant": bool(abs(t_stat) > 2.0),
    }


def _calculate_sharpe(returns: pd.Series) -> float:
    clean = returns.dropna()
    if len(clean) < 2:
        return 0.0
    std = float(clean.std())
    if std <= 1e-12:
        return 0.0
    return float((clean.mean() / std) * math.sqrt(252))


def walk_forward_backtest(
    data: pd.DataFrame,
    signal_func: Callable[[pd.DataFrame, Dict[str, Any]], pd.Series],
    train_days: int = 120,
    test_days: int = 30,
    step_days: int = 15,
    param_grid: Optional[List[Dict[str, Any]]] = None,
) -> List[WalkForwardResult]:
    """Walk-forward validation with strict train/test split and zero look-ahead bias."""
    if "close" not in data.columns:
        raise ValueError("DataFrame must include a 'close' column.")

    results: List[WalkForwardResult] = []
    grid = param_grid or [{}]
    total_len = len(data)

    for start_idx in range(0, max(1, total_len - train_days - test_days + 1), step_days):
        train_end = start_idx + train_days
        test_end = train_end + test_days
        if test_end > total_len:
            break

        train_df = data.iloc[start_idx:train_end]
        test_df = data.iloc[train_end:test_end]

        best_params: Dict[str, Any] = grid[0]
        best_train_sharpe = -999.0

        for candidate in grid:
            sig = signal_func(train_df, candidate)
            # Shift signal by 1 bar so signal at close[t] trades return[t+1] (no look-ahead)
            strat_ret = sig.shift(1).fillna(0.0) * train_df["close"].pct_change().fillna(0.0)
            sh = _calculate_sharpe(strat_ret)
            if sh > best_train_sharpe:
                best_train_sharpe = sh
                best_params = dict(candidate)

        test_sig = signal_func(test_df, best_params)
        test_ret = test_sig.shift(1).fillna(0.0) * test_df["close"].pct_change().fillna(0.0)
        test_sharpe = _calculate_sharpe(test_ret)
        n_trades = int((test_sig.diff().fillna(0.0) != 0).sum())

        results.append(
            WalkForwardResult(
                train_sharpe=round(best_train_sharpe, 4),
                test_sharpe=round(test_sharpe, 4),
                train_start=data.index[start_idx],
                train_end=data.index[train_end - 1],
                test_start=data.index[train_end],
                test_end=data.index[test_end - 1],
                params=best_params,
                trades=n_trades,
            )
        )

    return results


def analyze_walk_forward(results: List[WalkForwardResult]) -> Dict[str, Any]:
    """Summarize walk-forward out-of-sample stability and Sharpe degradation."""
    if not results:
        return {
            "avg_train_sharpe": 0.0,
            "avg_test_sharpe": 0.0,
            "sharpe_degradation": 1.0,
            "test_sharpe_std": 0.0,
            "pct_profitable_periods": 0.0,
            "worst_test_sharpe": 0.0,
            "total_periods": 0,
            "is_viable": False,
        }

    train_s = [r.train_sharpe for r in results]
    test_s = [r.test_sharpe for r in results]
    avg_train = float(np.mean(train_s))
    avg_test = float(np.mean(test_s))
    degradation = 1.0 - (avg_test / avg_train) if abs(avg_train) > 1e-6 else 0.0

    return {
        "avg_train_sharpe": round(avg_train, 4),
        "avg_test_sharpe": round(avg_test, 4),
        "sharpe_degradation": round(degradation, 4),
        "test_sharpe_std": round(float(np.std(test_s)), 4),
        "pct_profitable_periods": round(sum(1 for s in test_s if s > 0) / len(test_s), 4),
        "worst_test_sharpe": round(min(test_s), 4),
        "total_periods": len(results),
        "is_viable": bool(avg_test > 0.5 and (avg_train <= 0 or avg_test / avg_train > 0.5)),
    }


def estimate_transaction_costs(
    trade_value: float,
    trade_side: str,
    asset_class: str,
    avg_daily_volume: float,
    volatility: float,
    is_market_order: bool = True,
) -> Dict[str, float]:
    """Estimate all-in transaction costs (commission + spread + square-root market impact)."""
    if trade_value <= 0 or avg_daily_volume <= 0:
        raise ValueError("trade_value and avg_daily_volume must be positive.")

    commission_rates = {
        "us_equity": 0.0005,
        "crypto": 0.001,
        "futures": 0.00001,
        "forex": 0.00002,
    }
    spread_estimates = {
        "us_equity": 0.0003,
        "crypto": 0.001,
        "futures": 0.0001,
        "forex": 0.0001,
    }

    commission = trade_value * commission_rates.get(asset_class, 0.001)
    spread = spread_estimates.get(asset_class, 0.001) if is_market_order else 0.0
    spread_cost = trade_value * spread

    participation_rate = trade_value / avg_daily_volume
    market_impact = volatility * math.sqrt(participation_rate) * trade_value
    execution_days = max(1.0, trade_value / (avg_daily_volume * 0.1))
    timing_risk = volatility * math.sqrt(execution_days / 252.0) * trade_value
    total_cost = commission + spread_cost + market_impact

    return {
        "commission": round(commission, 4),
        "spread": round(spread_cost, 4),
        "market_impact": round(market_impact, 4),
        "timing_risk": round(timing_risk, 4),
        "total_cost": round(total_cost, 4),
        "cost_bps": round((total_cost / trade_value) * 10000.0, 2),
        "execution_days": round(execution_days, 2),
        "participation_rate": round(participation_rate, 6),
    }
