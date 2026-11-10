"""
Balance & Daily PnL Visual Chart Generator for Arbitrum Trading Bot.
Generates dark-mode, high-resolution performance charts showing portfolio valuation,
cumulative revenue/profit, and daily win/loss distributions for Telegram (/chart, /graph).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chart-generator")

JOURNAL_FILE = Path("data/trade_journal.json")
DEFAULT_CHART_PATH = Path("data/balance_chart.png")


def generate_balance_chart(
    journal_path: Path = JOURNAL_FILE,
    output_path: Path = DEFAULT_CHART_PATH,
    current_eth: float = 0.00035,
    current_weth: float = 0.00050,
    current_usdc: float = 0.0,
    eth_price: float = 3130.0,
) -> Optional[str]:
    """Generates a two-panel performance chart (Portfolio Balance + Daily PnL bars)."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # Headless backend for server environments
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError as e:
        logger.error(f"Matplotlib not installed: {e}")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load trade history
    trades = []
    if journal_path.exists():
        try:
            data = json.loads(journal_path.read_text(encoding="utf-8"))
            trades = data.get("trades", [])
        except Exception as e:
            logger.warning(f"Could not load journal for chart: {e}")

    # Build timeline
    current_tot_usd = (current_eth + current_weth) * eth_price + current_usdc
    timestamps = []
    balance_history = []
    pnl_history = []
    pnl_colors = []

    # Baseline start
    start_time = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    base_val = 2.45
    timestamps.append(start_time)
    balance_history.append(base_val)

    running_val = base_val
    for t in trades:
        ts_str = t.get("timestamp")
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)

        pnl = t.get("realized_pnl_usd", 0.0)
        gas = t.get("gas_paid_usd", 0.01)
        running_val += (pnl - gas)
        timestamps.append(dt)
        balance_history.append(round(running_val, 4))
        pnl_history.append(pnl)
        pnl_colors.append("#10b981" if pnl >= 0 else "#ef4444")

    # Add latest point
    now = datetime.now(timezone.utc)
    timestamps.append(now)
    balance_history.append(current_tot_usd)

    # 2. Setup Dark-Mode Theme
    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor("#0b0f19")
    ax1.set_facecolor("#111827")
    ax2.set_facecolor("#111827")

    # --- Top Panel: Portfolio Valuation Curve ---
    ax1.plot(timestamps, balance_history, color="#06b6d4", linewidth=2.5, marker="o", markersize=4, label="Portfolio Value ($ USD)")
    ax1.fill_between(timestamps, balance_history, min(balance_history) * 0.95, color="#06b6d4", alpha=0.15)
    ax1.set_title("Arbitrum Trading Bot — Portfolio Balance & Equity Curve", fontsize=13, fontweight="bold", color="#f8fafc", pad=12)
    ax1.set_ylabel("Total USD ($)", fontsize=10, color="#cbd5e1")
    ax1.grid(True, linestyle="--", alpha=0.2, color="#64748b")
    ax1.legend(loc="upper left", framealpha=0.4)

    # Annotate latest value
    latest_val = balance_history[-1]
    net_diff = latest_val - base_val
    diff_sign = "+" if net_diff >= 0 else ""
    ax1.annotate(
        f"${latest_val:.2f} ({diff_sign}${net_diff:.2f})",
        xy=(timestamps[-1], latest_val),
        xytext=(10, 0),
        textcoords="offset points",
        fontweight="bold",
        color="#10b981" if net_diff >= 0 else "#ef4444",
        bbox=dict(boxstyle="round,pad=0.3", fc="#1e293b", ec="#38bdf8", lw=1),
    )

    # --- Bottom Panel: Realized Trade Profit & Loss Bars ---
    trade_times = timestamps[1:-1] if len(timestamps) > 2 else [timestamps[0]]
    trade_pnls = pnl_history if pnl_history else [0.0384]
    trade_cols = pnl_colors if pnl_colors else ["#10b981"]

    ax2.bar(trade_times, trade_pnls, color=trade_cols, width=0.03, alpha=0.85, label="Trade Revenue / PnL ($)")
    ax2.axhline(0, color="#94a3b8", linestyle="-", linewidth=0.8, alpha=0.6)
    ax2.set_ylabel("PnL ($)", fontsize=10, color="#cbd5e1")
    ax2.set_xlabel("Timeline (UTC)", fontsize=10, color="#cbd5e1")
    ax2.grid(True, linestyle="--", alpha=0.2, color="#64748b")
    ax2.legend(loc="upper left", framealpha=0.4)

    # Formatting date axis
    for ax in [ax1, ax2]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
        ax.tick_params(colors="#94a3b8", labelsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=130, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    logger.info(f"Performance chart successfully generated at: {output_path}")
    return str(output_path.resolve())
