"""
Accuracy & Decision Intelligence Tracker for Arbitrum Trading Bot.
Maintains persistent trade journal, computes quantitative performance metrics (Win Rate,
Profit Factor, Sharpe, Gas Efficiency), and generates transparent explainability reports
for Telegram (/accuracy, /decision, /plan).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("accuracy-tracker")

JOURNAL_FILE = Path("data/trade_journal.json")


class AccuracyTracker:
    def __init__(self, journal_path: Path = JOURNAL_FILE):
        self.journal_path = journal_path
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.trades: List[Dict[str, Any]] = []
        self._load_journal()

    def _load_journal(self) -> None:
        if self.journal_path.exists():
            try:
                data = json.loads(self.journal_path.read_text(encoding="utf-8"))
                self.trades = data.get("trades", [])
            except Exception as e:
                logger.error(f"Error reading trade journal: {e}")
                self.trades = []
        else:
            self._save_journal()

    def _save_journal(self) -> None:
        try:
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "trades_count": len(self.trades),
                "trades": self.trades,
            }
            self.journal_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error saving trade journal: {e}")

    def record_swap(
        self,
        action: str,
        token_in: str,
        token_out: str,
        amount_in: float,
        amount_out: float,
        price_usd: float,
        gas_paid_usd: float,
        tx_hash: str,
        block_number: int,
        decision_rationale: str,
        conviction_pct: float,
    ) -> Dict[str, Any]:
        """Record an executed swap and calculate roundtrip PnL if completing a cycle."""
        entry_value_usd = (amount_in * price_usd) if token_in == "WETH" else amount_in
        exit_value_usd = (amount_out * price_usd) if token_out == "WETH" else amount_out

        trade_record: Dict[str, Any] = {
            "id": len(self.trades) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "amount_out": amount_out,
            "price_usd": price_usd,
            "gas_paid_usd": gas_paid_usd,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "decision_rationale": decision_rationale,
            "conviction_pct": conviction_pct,
            "trade_value_usd": max(entry_value_usd, exit_value_usd),
        }

        # Check if closing a round-trip position (e.g. WETH -> USDC exit)
        if token_in == "WETH" and token_out == "USDC":
            # Match with most recent buy
            prev_buys = [t for t in self.trades if t["token_out"] == "WETH" and "pnl_usd" not in t]
            if prev_buys:
                matched_buy = prev_buys[-1]
                buy_cost = matched_buy["amount_in"]  # USDC spent
                sell_proceeds = amount_out  # USDC received
                net_pnl = sell_proceeds - buy_cost - gas_paid_usd - matched_buy.get("gas_paid_usd", 0.0)
                trade_record["realized_pnl_usd"] = round(net_pnl, 4)
                trade_record["is_win"] = net_pnl > 0
                trade_record["pnl_pct"] = round((net_pnl / buy_cost) * 100.0, 2) if buy_cost > 0 else 0.0

        self.trades.append(trade_record)
        self._save_journal()
        return trade_record

    def get_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive quantitative accuracy statistics."""
        total_swaps = len(self.trades)
        closed_trades = [t for t in self.trades if "realized_pnl_usd" in t]

        wins = [t for t in closed_trades if t.get("is_win", False)]
        losses = [t for t in closed_trades if not t.get("is_win", False)]

        gross_profit = sum(t["realized_pnl_usd"] for t in wins)
        gross_loss = abs(sum(t["realized_pnl_usd"] for t in losses))
        total_gas = sum(t.get("gas_paid_usd", 0.0) for t in self.trades)

        win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 100.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        net_pnl = gross_profit - gross_loss

        return {
            "total_swaps": total_swaps,
            "closed_roundtrips": len(closed_trades),
            "wins_count": len(wins),
            "losses_count": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "gross_profit_usd": round(gross_profit, 4),
            "gross_loss_usd": round(gross_loss, 4),
            "profit_factor": round(profit_factor, 2),
            "total_gas_usd": round(total_gas, 4),
            "net_pnl_usd": round(net_pnl, 4),
        }

    def format_accuracy_report(self) -> str:
        """Generate Telegram HTML report for /accuracy or /stats."""
        m = self.get_metrics()
        win_icon = "🎯" if m["win_rate_pct"] >= 60.0 else "⚠️"
        pnl_sign = "+" if m["net_pnl_usd"] >= 0 else ""

        report = (
            "🎯 <b>QUANTITATIVE ACCURACY & PERFORMANCE METRICS</b>\n\n"
            f"• <b>Total Swaps Executed:</b> <code>{m['total_swaps']}</code>\n"
            f"• <b>Completed Cycles:</b> <code>{m['closed_roundtrips']}</code>\n"
            f"• <b>Win / Loss:</b> 🟢 <code>{m['wins_count']}</code> / 🔴 <code>{m['losses_count']}</code>\n"
            f"• <b>Win Rate:</b> {win_icon} <b>{m['win_rate_pct']}%</b>\n\n"
            "<b>Financial Efficiency:</b>\n"
            f"• Gross Gains: <code>+${m['gross_profit_usd']:.4f} USD</code>\n"
            f"• Gross Losses: <code>-${m['gross_loss_usd']:.4f} USD</code>\n"
            f"• Profit Factor: <b>{m['profit_factor']:.2f}x</b>\n"
            f"• Total Gas Paid (L2): <code>${m['total_gas_usd']:.4f} USD</code> (~1¢/tx)\n"
            f"• <b>Realized Net PnL:</b> <b>{pnl_sign}${m['net_pnl_usd']:.4f} USD</b>\n\n"
            "<i>Metrics update continuously with every confirmed on-chain swap.</i>"
        )
        return report

    def format_decision_report(self, state: Dict[str, Any]) -> str:
        """Generate Telegram HTML report explaining current decision logic (/decision or /why)."""
        regime = state.get("regime", "NEUTRAL_MONITORING")
        spot = state.get("spot_px", 3120.0)
        ma5 = state.get("short_ma", 3120.0)
        ma10 = state.get("long_ma", 3120.0)
        rsi = state.get("rsi", 50.0)
        conviction = state.get("conviction_pct", 75.0)
        action = state.get("action", "HOLDING")
        rationale = state.get("rationale", "Analyzing on-chain order flow and moving average trends.")
        next_trigger = state.get("next_trigger", "Waiting for MA crossover or RSI extreme.")

        regime_icon = "🟢" if "BULL" in regime else ("🔴" if "BEAR" in regime else "🟡")

        report = (
            f"🧠 <b>BOT DECISION INTELLIGENCE BREAKDOWN</b>\n\n"
            f"<b>Current Market State:</b>\n"
            f"• ETH Spot Price: <code>${spot:.2f} USD</code>\n"
            f"• Market Regime: {regime_icon} <b>{regime}</b>\n"
            f"• AI Conviction Score: <b>{conviction:.1f}%</b>\n\n"
            "<b>Technical Indicators:</b>\n"
            f"• Fast MA (5-period): <code>${ma5:.2f}</code>\n"
            f"• Slow MA (10-period): <code>${ma10:.2f}</code>\n"
            f"• RSI (14-period): <code>{rsi:.1f}</code> "
            f"({'Oversold 🟢' if rsi < 35 else ('Overbought 🔴' if rsi > 65 else 'Neutral ⚖️')})\n\n"
            f"<b>Current Position Action:</b> <b>{action}</b>\n\n"
            f"💡 <b>Decision Logic:</b>\n<i>{rationale}</i>\n\n"
            f"🎯 <b>Next Execution Trigger:</b>\n<code>{next_trigger}</code>"
        )
        return report

    def format_plan_report(self) -> str:
        """Generate Telegram HTML report for strategic future roadmap (/plan)."""
        plan = (
            "🗺️ <b>STRATEGIC FUTURE PLAN & CAPITAL ROADMAP</b>\n\n"
            "<b>Phase 1: Micro-Capital Validation ($2.70 ➔ $50)</b> [CURRENT]\n"
            "• Arbitrum One L2 gas optimization (~$0.01 per swap)\n"
            "• Uniswap v3 0.05% fee pool execution\n"
            "• Testing MA crossover + RSI momentum filtering\n"
            "• Circuit-breaker gas floor (0.00005 ETH)\n\n"
            "<b>Phase 2: Multi-Pair Expansion ($50 ➔ $500)</b>\n"
            "• Expand beyond ETH/USDC to ARB/USDC and WBTC/USDC\n"
            "• Dynamic fractional Kelly-Criterion position sizing\n"
            "• Slippage protection dynamic adjustment (0.1% - 0.5%)\n\n"
            "<b>Phase 3: Volatility & MEV Shield ($500 ➔ $2,000)</b>\n"
            "• Bollinger Bands & ATR-based volatility breakouts\n"
            "• Trailing take-profit and stop-loss execution\n"
            "• Private RPC routing to prevent sandwich attacks\n\n"
            "<b>Phase 4: Multi-Agent Consensus ($2,000+)</b>\n"
            "• Multi-agent deliberation pipeline (Technical + Risk + On-Chain flow)\n"
            "• Automated yield compounding into Aave v3 Arbitrum pools"
        )
        return plan
