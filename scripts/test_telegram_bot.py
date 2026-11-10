"""
Test Telegram Bot connectivity and send test alert.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from core.notifications.telegram_notifier import TelegramNotifier

ENV_PATH = Path(".env")


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                bot_token = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)

    if not notifier.is_configured:
        print("[-] Telegram bot is not configured yet.")
        print("    Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        sys.exit(1)

    print(f"[*] Testing Telegram bot token: {bot_token[:8]}...")
    print(f"[*] Target Chat ID: {chat_id}")

    test_msg = (
        "🚀 <b>Telegram Bot Test Successful!</b>\n\n"
        "Your Arbitrum autonomous trading bot is successfully linked to this chat.\n"
        "You will receive:\n"
        "• Real-time on-chain trade alerts with Arbiscan links\n"
        "• Daily balance & PnL performance reports\n"
        "• Instant error & circuit breaker notifications"
    )

    success = notifier.send_message(test_msg)
    if success:
        print("[+] Test message successfully delivered to Telegram!")
    else:
        print("[-] Failed to deliver message. Please check token and chat ID.")


if __name__ == "__main__":
    main()
