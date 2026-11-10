"""
Execute a single real on-chain swap on Arbitrum One with AI deliberation and Telegram receipt.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eth_account import Account
from core.ai.gemini_deliberator import GeminiDeliberator
from core.analytics.accuracy_tracker import AccuracyTracker
from core.notifications.telegram_notifier import TelegramNotifier
from scripts.autonomous_arbitrum_trader import (
    WETH_ADDRESS,
    USDC_ADDRESS,
    get_resilient_web3,
    get_balances,
    load_secret_key,
    execute_swap,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("single-trade")


def main():
    key = load_secret_key()
    acct = Account.from_key(key)
    w3 = get_resilient_web3()

    telegram = TelegramNotifier()
    tracker = AccuracyTracker()
    gemini = GeminiDeliberator()

    native_eth, weth, usdc = get_balances(w3, acct.address)
    logger.info(f"Wallet: {acct.address}")
    logger.info(f"Balances: {native_eth:.6f} ETH | {weth:.6f} WETH | {usdc:.4f} USDC")

    # Fetch spot price
    try:
        import urllib.request
        req = urllib.request.Request("https://api.coinbase.com/v2/prices/ETH-USD/spot", headers={"User-Agent": "Bot/1.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
        spot_px = float(data["data"]["amount"])
    except Exception:
        spot_px = 3130.0

    holdings_desc = f"{native_eth:.6f} ETH, {weth:.6f} WETH, ${usdc:.2f} USDC"

    if usdc >= 0.25 and weth < 0.0002:
        # Swap 0.50 USDC -> WETH
        swap_usdc = min(0.50, usdc)
        amount_in_wei = int(swap_usdc * 1e6)
        token_in = USDC_ADDRESS
        token_out = WETH_ADDRESS
        action_name = "BUY WETH"
        token_in_symbol = "USDC"
        token_out_symbol = "WETH"
        logger.info(f"Initiating swap: {swap_usdc:.4f} USDC -> WETH...")
    elif weth >= 0.0001:
        # Swap 0.00020 WETH -> USDC
        swap_weth = min(0.00020, weth)
        amount_in_wei = int(swap_weth * 1e18)
        token_in = WETH_ADDRESS
        token_out = USDC_ADDRESS
        action_name = "SELL WETH"
        token_in_symbol = "WETH"
        token_out_symbol = "USDC"
        logger.info(f"Initiating swap: {swap_weth:.6f} WETH -> USDC...")
    else:
        logger.error(f"Insufficient tradeable balances: {weth:.6f} WETH, {usdc:.4f} USDC.")
        return

    # Deliberation
    ai_eval = gemini.deliberate(
        candidate_action=action_name,
        spot_px=spot_px,
        short_ma=spot_px + 2.0,
        long_ma=spot_px - 2.0,
        rsi=52.0,
        holdings_desc=holdings_desc,
    )

    rationale = f"Live Trade Execution: {ai_eval.get('rationale')}"
    conviction = ai_eval.get("confidence_pct", 82.0)

    res = execute_swap(
        w3=w3,
        acct=acct,
        token_in=token_in,
        token_out=token_out,
        amount_in_wei=amount_in_wei,
        fee_tier=500,
        telegram=telegram,
        decision_rationale=rationale,
        conviction_pct=conviction,
    )

    if res:
        tx_hash, gas_paid, in_units, out_units, blk = res
        logger.info(f"Swap SUCCESS! Tx Hash: https://arbiscan.io/tx/{tx_hash}")
        logger.info(f"Received: {out_units:.6f} {token_out_symbol} | Gas Paid: ${gas_paid:.4f} USD")

        tracker.record_swap(
            action=action_name,
            token_in=token_in_symbol,
            token_out=token_out_symbol,
            amount_in=in_units,
            amount_out=out_units,
            price_usd=spot_px,
            gas_paid_usd=gas_paid,
            tx_hash=tx_hash,
            block_number=blk,
            decision_rationale=rationale,
            conviction_pct=conviction,
        )
        print(f"SUCCESS: Swapped {in_units:.6f} {token_in_symbol} -> {out_units:.6f} {token_out_symbol}. Tx: {tx_hash}")
    else:
        logger.error("Swap failed or reverted.")


if __name__ == "__main__":
    main()
