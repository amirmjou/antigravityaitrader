"""
Telegram Notification & Command Interface for Arbitrum Trading Bot.
Uses pure HTTP (urllib.request) to send real-time trade receipts, daily PnL summaries,
and error alerts, plus polls for interactive commands (/balance, /status, /report) without open ports.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("telegram-notifier")


class TelegramNotifier:
    """Resilient Telegram Bot client for trade alerts, daily summaries, and health alerts."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()

        if not self.bot_token or not self.chat_id:
            from pathlib import Path
            for env_candidate in [Path(".env"), Path("/etc/tradingbot/tradingbot.env")]:
                if env_candidate.exists():
                    try:
                        for line in env_candidate.read_text(encoding="utf-8").splitlines():
                            line = line.strip()
                            if line.startswith("TELEGRAM_BOT_TOKEN=") and not self.bot_token:
                                self.bot_token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            elif line.startswith("TELEGRAM_CHAT_ID=") and not self.chat_id:
                                self.chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
                    except Exception:
                        pass

        self.api_base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self._last_update_id = 0
        self._command_handlers: Dict[str, Callable[[], str]] = {}
        self._polling_active = False

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and len(self.bot_token) > 15)

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.is_configured:
            logger.debug("Telegram not configured. Skipping alert.")
            return False

        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "ArbitrumTraderBot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return bool(res.get("ok"))
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def send_startup_alert(self, address: str, native_eth: float, usdc: float, network: str = "Arbitrum One") -> bool:
        """Notify user that the bot has started or rebooted on Google Cloud."""
        total_usd = native_eth * 3120.0 + usdc
        msg = (
            "🤖 <b>Arbitrum Trading Bot — ONLINE 24/7</b>\n\n"
            f"<b>Server:</b> Google Cloud Platform\n"
            f"<b>Network:</b> {network} (Chain ID 42161)\n"
            f"<b>Wallet Address:</b> <code>{address}</code>\n\n"
            f"<b>Active Balances:</b>\n"
            f"• Native ETH: <code>{native_eth:.6f} ETH</code> (Gas Reserve)\n"
            f"• USDC: <code>${usdc:.2f} USDC</code>\n"
            f"• Total Value: <b>~${total_usd:.2f} USD</b>\n\n"
            f"🔗 <a href='https://arbiscan.io/address/{address}'>View Wallet on Arbiscan</a>\n\n"
            "<i>Commands: /balance, /status, /report, /ping</i>"
        )
        return self.send_message(msg)

    def send_trade_receipt(
        self,
        action: str,
        token_in_name: str,
        token_out_name: str,
        amount_in: float,
        amount_out: float,
        tx_hash: str,
        gas_paid_usd: float,
        block_number: int,
        decision_rationale: Optional[str] = None,
        conviction_pct: Optional[float] = None,
    ) -> bool:
        """Notify user of a completed on-chain swap with direct Arbiscan link & decision rationale."""
        icon = "🟢" if "USDC ->" in f"{token_in_name} -> {token_out_name}" else "🔵"
        msg = (
            f"{icon} <b>REAL ON-CHAIN SWAP EXECUTED!</b>\n\n"
            f"<b>Action:</b> {action} ({token_in_name} ➔ {token_out_name})\n"
            f"<b>Sold:</b> <code>{amount_in:.6f} {token_in_name}</code>\n"
            f"<b>Received:</b> <code>{amount_out:.4f} {token_out_name}</code>\n"
            f"<b>Block:</b> <code>{block_number}</code>\n"
            f"<b>Gas Fee Paid:</b> <code>${gas_paid_usd:.4f} USD</code> (~1¢)\n"
        )
        if conviction_pct is not None:
            msg += f"<b>Conviction Score:</b> <code>{conviction_pct:.1f}%</code>\n"
        if decision_rationale:
            msg += f"🧠 <b>Decision Logic:</b> <i>{decision_rationale}</i>\n"

        msg += f"\n🔗 <a href='https://arbiscan.io/tx/{tx_hash}'>Verify on Arbiscan</a>"
        return self.send_message(msg)

    def send_daily_summary(
        self,
        starting_bal_usd: float,
        current_bal_usd: float,
        net_pnl_usd: float,
        trades_count: int,
        total_gas_usd: float,
        wallet_address: str,
    ) -> bool:
        """Send daily performance summary report."""
        pnl_sign = "+" if net_pnl_usd >= 0 else ""
        pnl_icon = "📈" if net_pnl_usd >= 0 else "📉"
        pnl_pct = ((current_bal_usd - starting_bal_usd) / starting_bal_usd * 100.0) if starting_bal_usd > 0 else 0.0

        msg = (
            f"📊 <b>DAILY TRADING SUMMARY REPORT</b>\n\n"
            f"<b>Date:</b> {time.strftime('%Y-%m-%d UTC')}\n"
            f"<b>Trades Executed Today:</b> {trades_count}\n"
            f"<b>Total Gas Spent:</b> <code>${total_gas_usd:.4f} USD</code>\n\n"
            f"<b>Portfolio Performance:</b>\n"
            f"• Starting Balance: <code>${starting_bal_usd:.2f} USD</code>\n"
            f"• Current Balance: <b>${current_bal_usd:.2f} USD</b>\n"
            f"• Daily Net PnL: {pnl_icon} <b>{pnl_sign}${net_pnl_usd:.2f} ({pnl_sign}{pnl_pct:.1f}%)</b>\n\n"
            f"🔗 <a href='https://arbiscan.io/address/{wallet_address}'>Arbiscan Explorer</a>"
        )
        return self.send_message(msg)

    def send_error_alert(self, component: str, error_message: str, details: Optional[str] = None) -> bool:
        """Instant alert if an issue occurs in the trading bot, RPC, or server."""
        msg = (
            f"🚨 <b>TRADING BOT ALERT: ISSUE DETECTED</b>\n\n"
            f"<b>Component:</b> {component}\n"
            f"<b>Error:</b> <code>{error_message}</code>\n"
        )
        if details:
            msg += f"\n<b>Details:</b> <code>{details[:300]}</code>\n"
        msg += "\n<i>The system will auto-retry via exponential backoff and circuit breakers.</i>"
        return self.send_message(msg)

    def register_command(self, command: str, handler: Callable[[], str]) -> None:
        """Register a handler for a command like /balance, /status, etc."""
        self._command_handlers[command.lower().strip()] = handler

    def start_polling_in_background(self) -> None:
        """Start long-polling in a background thread to receive commands without open ports."""
        if not self.is_configured:
            return
        if self._polling_active:
            return

        self._polling_active = True
        thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramPollThread")
        thread.start()
        logger.info("Telegram command polling thread started.")

    def _poll_loop(self) -> None:
        while self._polling_active:
            try:
                url = f"{self.api_base}/getUpdates?offset={self._last_update_id + 1}&timeout=15"
                req = urllib.request.Request(url, headers={"User-Agent": "ArbitrumTraderBot/1.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    updates = data.get("result", [])

                    for u in updates:
                        self._last_update_id = u["update_id"]
                        message = u.get("message", {})
                        text = message.get("text", "").strip()
                        chat = message.get("chat", {})
                        sender_chat_id = str(chat.get("id", ""))

                        # Only respond to authorized chat_id
                        if str(self.chat_id) and sender_chat_id != str(self.chat_id):
                            continue

                        if text.startswith("/"):
                            cmd = text.split()[0].lower()
                            handler = self._command_handlers.get(cmd)
                            if handler:
                                try:
                                    response_text = handler()
                                    self.send_message(response_text)
                                except Exception as err:
                                    self.send_message(f"⚠️ Error executing {cmd}: {err}")
                            elif cmd in ["/help", "/start"]:
                                help_msg = (
                                    "👋 <b>Arbitrum Bot Command List:</b>\n\n"
                                    "🧠 <b>Intelligence & Explainability:</b>\n"
                                    "• <code>/decision</code> — Why the bot is holding/swapping right now\n"
                                    "• <code>/accuracy</code> — Win rate %, profit factor, and metrics\n"
                                    "• <code>/plan</code> — Future roadmap & capital scaling strategy\n\n"
                                    "💰 <b>Portfolio & Reports:</b>\n"
                                    "• <code>/balance</code> — Live on-chain Arbitrum balances\n"
                                    "• <code>/report</code> — Today's trade count & PnL\n"
                                    "• <code>/status</code> — System and RPC health\n"
                                    "• <code>/ping</code> — Verify bot is alive"
                                )
                                self.send_message(help_msg)
            except Exception as e:
                time.sleep(5)
