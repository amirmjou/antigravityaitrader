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

    # We hold 0.000498 WETH -> Swap 0.000250 WETH into USDC
    swap_weth = 0.000250
    if weth < swap_weth:
        logger.error(f"Insufficient WETH balance ({weth:.6f} < {swap_weth}).")
        return

    amount_in_wei = int(swap_weth * 1e18)
    spot_px = 3130.0

    # 1. Deliberation
    holdings_desc = f"{native_eth:.6f} ETH, {weth:.6f} WETH, ${usdc:.2f} USDC"
    ai_eval = gemini.deliberate(
        candidate_action="BUY USDC (PARTIAL REBALANCE)",
        spot_px=spot_px,
        short_ma=3135.0,
        long_ma=3125.0,
        rsi=55.0,
        holdings_desc=holdings_desc,
    )

    rationale = f"Live Trade Execution: {ai_eval.get('rationale')}"
    conviction = ai_eval.get("confidence_pct", 80.0)

    logger.info(f"Executing swap: {swap_weth:.6f} WETH ➔ USDC...")
    res = execute_swap(
        w3=w3,
        acct=acct,
        token_in=WETH_ADDRESS,
        token_out=USDC_ADDRESS,
        amount_in_wei=amount_in_wei,
        fee_tier=500,
        telegram=telegram,
        decision_rationale=rationale,
        conviction_pct=conviction,
    )

    if res:
        tx_hash, gas_paid, in_units, out_units, blk = res
        logger.info(f"Swap SUCCESS! Tx Hash: https://arbiscan.io/tx/{tx_hash}")
        logger.info(f"Received: {out_units:.4f} USDC | Gas Paid: ${gas_paid:.4f} USD")

        tracker.record_swap(
            action="BUY USDC",
            token_in="WETH",
            token_out="USDC",
            amount_in=in_units,
            amount_out=out_units,
            price_usd=spot_px,
            gas_paid_usd=gas_paid,
            tx_hash=tx_hash,
            block_number=blk,
            decision_rationale=rationale,
            conviction_pct=conviction,
        )
        print(f"SUCCESS: Swapped {in_units:.6f} WETH -> {out_units:.4f} USDC. Tx: {tx_hash}")
    else:
        logger.error("Swap failed or reverted.")


if __name__ == "__main__":
    main()
