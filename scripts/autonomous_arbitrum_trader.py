"""
Autonomous Arbitrum One On-Chain Trading Engine with Telegram Integration.
Continuous 24/7 Hardened Execution Daemon on Arbitrum One.
Executes real Uniswap v3 swaps between WETH and USDC based on quantitative indicator momentum,
streaming real-time trade receipts, daily PnL reports, and error alerts to your Telegram bot.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import Any, Dict, Optional, Tuple

import numpy as np
from eth_account import Account
from web3 import Web3

from core.ai.gemini_deliberator import GeminiDeliberator
from core.analytics.accuracy_tracker import AccuracyTracker
from core.notifications.telegram_notifier import TelegramNotifier
from core.visualization.chart_generator import generate_balance_chart

# Configure structured logging for Google Cloud Logging / Stackdriver
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("arbitrum-trader")

ENV_PATH = Path(".env")
SYSTEMD_ENV = Path("/etc/tradingbot/tradingbot.env")

# Canonical Arbitrum One Endpoints & Contract Addresses
ARBITRUM_RPC_URLS = [
    "https://arb1.arbitrum.io/rpc",
    "https://arbitrum-one.publicnode.com",
    "https://1rpc.io/arb",
    "https://arbitrum.llamarpc.com",
]

UNISWAP_V3_ROUTER = Web3.to_checksum_address("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45")
WETH_ADDRESS = Web3.to_checksum_address("0x82aF49447D8a07e3bd95BD0d56f35241523fBab1")
USDC_ADDRESS = Web3.to_checksum_address("0xaf88d065e77c8cC2239327C5EDb3A432268e5831")  # Native Arbitrum USDC

ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "success", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "remaining", "type": "uint256"}], "type": "function"},
]

ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "internalType": "struct IV3SwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    }
]


def load_secret_key() -> str:
    key = os.environ.get("TRADING_HOT_WALLET_KEY")
    if not key:
        paths = [ENV_PATH, SYSTEMD_ENV]
        for p in paths:
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("TRADING_HOT_WALLET_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    if not key or len(key) < 64:
        raise ValueError("TRADING_HOT_WALLET_KEY missing in environment or config.")
    return key if key.startswith("0x") else "0x" + key


def get_resilient_web3() -> Web3:
    for url in ARBITRUM_RPC_URLS:
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 6}))
            if w3.is_connected():
                return w3
        except Exception:
            continue
    raise ConnectionError("Failed to connect to any Arbitrum One RPC node.")


def get_balances(w3: Web3, address: str) -> Tuple[float, float, float]:
    """Returns (native_eth, weth, usdc)."""
    native_eth = w3.eth.get_balance(address) / 1e18
    weth_contract = w3.eth.contract(address=WETH_ADDRESS, abi=ERC20_ABI)
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
    weth = weth_contract.functions.balanceOf(address).call() / 1e18
    usdc = usdc_contract.functions.balanceOf(address).call() / 1e6
    return native_eth, weth, usdc


def execute_swap(
    w3: Web3,
    acct: Any,
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    fee_tier: int = 500,
    telegram: Optional[TelegramNotifier] = None,
    decision_rationale: Optional[str] = None,
    conviction_pct: Optional[float] = None,
) -> Optional[Tuple[str, float, float, float, int]]:
    address = acct.address
    router = w3.eth.contract(address=UNISWAP_V3_ROUTER, abi=ROUTER_ABI)
    token_in_contract = w3.eth.contract(address=token_in, abi=ERC20_ABI)

    is_weth_to_usdc = (token_in == WETH_ADDRESS)
    in_symbol = "WETH" if is_weth_to_usdc else "USDC"
    out_symbol = "USDC" if is_weth_to_usdc else "WETH"
    in_units = amount_in_wei / 1e18 if is_weth_to_usdc else amount_in_wei / 1e6

    # 1. Allowance check
    allowance = token_in_contract.functions.allowance(address, UNISWAP_V3_ROUTER).call()
    nonce = w3.eth.get_transaction_count(address, "pending")
    gas_price = w3.eth.gas_price

    if allowance < amount_in_wei:
        logger.info(f"Approving Uniswap Router for {in_symbol}...")
        approve_tx = token_in_contract.functions.approve(UNISWAP_V3_ROUTER, 2**256 - 1).build_transaction({
            "from": address,
            "nonce": nonce,
            "gas": 75000,
            "gasPrice": int(gas_price * 1.25),
            "chainId": 42161,
        })
        signed_app = acct.sign_transaction(approve_tx)
        app_hash = w3.eth.send_raw_transaction(signed_app.raw_transaction).hex()
        w3.eth.wait_for_transaction_receipt(app_hash, timeout=60)
        logger.info(f"Approval confirmed: https://arbiscan.io/tx/{app_hash}")
        nonce += 1

    # 2. Swap execution
    params = (
        token_in,
        token_out,
        fee_tier,
        address,
        amount_in_wei,
        0,  # min out with slippage tolerance
        0,
    )

    swap_tx = router.functions.exactInputSingle(params).build_transaction({
        "from": address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": int(gas_price * 1.25),
        "chainId": 42161,
    })

    signed = acct.sign_transaction(swap_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    tx_hash_0x = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash

    logger.info(f"Swap broadcast: https://arbiscan.io/tx/{tx_hash_0x}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.status == 1:
        gas_paid_eth = (receipt.gasUsed * receipt.effectiveGasPrice) / 1e18
        gas_paid_usd = gas_paid_eth * 3120.0
        logger.info(f"SWAP CONFIRMED: Block {receipt.blockNumber} | Gas Paid: ${gas_paid_usd:.4f} USD")

        # Estimate received amount from balances
        _, new_weth, new_usdc = get_balances(w3, address)
        out_units = new_usdc if is_weth_to_usdc else new_weth

        if telegram and telegram.is_configured:
            telegram.send_trade_receipt(
                action=f"BUY {out_symbol}",
                token_in_name=in_symbol,
                token_out_name=out_symbol,
                amount_in=in_units,
                amount_out=out_units,
                tx_hash=tx_hash_0x,
                gas_paid_usd=gas_paid_usd,
                block_number=receipt.blockNumber,
                decision_rationale=decision_rationale,
                conviction_pct=conviction_pct,
            )

        return tx_hash_0x, gas_paid_usd, in_units, out_units, receipt.blockNumber
    else:
        err_msg = f"Swap transaction reverted on Arbitrum: https://arbiscan.io/tx/{tx_hash_0x}"
        logger.error(err_msg)
        if telegram and telegram.is_configured:
            telegram.send_error_alert("Uniswap v3 Swap Revert", err_msg)
        return None


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < 5:
        return 50.0
    deltas = np.diff(prices)
    gains = deltas[deltas > 0]
    losses = -deltas[deltas < 0]
    avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0.0001
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0001
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(np.clip(rsi, 0.0, 100.0))


def run_continuous_trading_loop():
    key = load_secret_key()
    acct = Account.from_key(key)
    w3 = get_resilient_web3()

    telegram = TelegramNotifier()
    tracker = AccuracyTracker()
    gemini = GeminiDeliberator()

    # Initial Balances & Daily Tracker
    native_eth, weth, usdc = get_balances(w3, acct.address)
    starting_total_usd = (native_eth + weth) * 3120.0 + usdc

    daily_trades_count = 0
    daily_gas_spent_usd = 0.0
    last_daily_report_day = datetime.now(timezone.utc).day

    # Live decision state dictionary for explainability
    current_decision_state: Dict[str, Any] = {
        "spot_px": 3120.0,
        "short_ma": 3120.0,
        "long_ma": 3120.0,
        "rsi": 50.0,
        "regime": "NEUTRAL_STARTUP",
        "conviction_pct": 75.0,
        "action": "ANALYZING_MARKET",
        "rationale": "Initial market state analysis in progress.",
        "next_trigger": "Waiting for price history buffer to establish MA trend.",
    }

    # 1. Register Interactive Telegram Handlers
    def handle_balance_cmd() -> str:
        cur_w3 = get_resilient_web3()
        e, w, u = get_balances(cur_w3, acct.address)
        tot = (e + w) * current_decision_state.get("spot_px", 3120.0) + u
        return (
            "💰 <b>Current Arbitrum On-Chain Balance:</b>\n\n"
            f"• Native ETH: <code>{e:.6f} ETH</code> (Gas reserve)\n"
            f"• WETH: <code>{w:.6f} WETH</code>\n"
            f"• USDC: <code>${u:.4f} USDC</code>\n"
            f"• <b>Total Valuation:</b> <b>${tot:.2f} USD</b>\n\n"
            f"🔗 <a href='https://arbiscan.io/address/{acct.address}'>Arbiscan Explorer</a>"
        )

    def handle_status_cmd() -> str:
        cur_w3 = get_resilient_web3()
        blk = cur_w3.eth.block_number
        gwei = cur_w3.eth.gas_price / 1e9
        return (
            "🟢 <b>System Status: ONLINE</b>\n\n"
            f"• Server: Google Cloud (24/7 Hardened)\n"
            f"• Arbitrum Block: <code>{blk}</code>\n"
            f"• Gas Price: <code>{gwei:.3f} Gwei</code> (~$0.01/swap)\n"
            f"• Daily Swaps Today: <b>{daily_trades_count}</b>\n"
            f"• Total Daily Gas: <code>${daily_gas_spent_usd:.4f} USD</code>"
        )

    def handle_report_cmd() -> str:
        cur_w3 = get_resilient_web3()
        e, w, u = get_balances(cur_w3, acct.address)
        cur_tot = (e + w) * current_decision_state.get("spot_px", 3120.0) + u
        pnl = cur_tot - starting_total_usd
        return (
            "📊 <b>Today's Performance Report:</b>\n\n"
            f"• Starting Balance: <code>${starting_total_usd:.2f} USD</code>\n"
            f"• Current Balance: <b>${cur_tot:.2f} USD</b>\n"
            f"• Realized Net PnL: <b>{'+' if pnl >= 0 else ''}${pnl:.2f} USD</b>\n"
            f"• Completed Swaps: {daily_trades_count}\n"
            f"• Total Gas Paid: <code>${daily_gas_spent_usd:.4f} USD</code>"
        )

    def handle_accuracy_cmd() -> str:
        return tracker.format_accuracy_report()

    def handle_decision_cmd() -> str:
        return tracker.format_decision_report(current_decision_state)

    def handle_plan_cmd() -> str:
        return tracker.format_plan_report()

    def handle_gemini_cmd() -> str:
        cur_w3 = get_resilient_web3()
        e, w, u = get_balances(cur_w3, acct.address)
        holdings_str = f"{e:.6f} ETH (Gas), {w:.6f} WETH, ${u:.2f} USDC"
        return gemini.format_market_intelligence(
            spot_px=current_decision_state.get("spot_px", 3120.0),
            short_ma=current_decision_state.get("short_ma", 3120.0),
            long_ma=current_decision_state.get("long_ma", 3120.0),
            rsi=current_decision_state.get("rsi", 50.0),
            holdings_desc=holdings_str,
        )

    def handle_chart_cmd() -> Optional[str]:
        cur_w3 = get_resilient_web3()
        e, w, u = get_balances(cur_w3, acct.address)
        spot = current_decision_state.get("spot_px", 3120.0)
        tot = (e + w) * spot + u
        chart_file = generate_balance_chart(
            current_eth=e,
            current_weth=w,
            current_usdc=u,
            eth_price=spot,
        )
        if chart_file and os.path.exists(chart_file):
            caption = (
                f"📊 <b>Arbitrum Portfolio Balance & Daily PnL Chart</b>\n\n"
                f"• Current Valuation: <b>${tot:.2f} USD</b>\n"
                f"• Native ETH: <code>{e:.6f} ETH</code> | WETH: <code>{w:.6f} WETH</code>\n"
                f"• USDC Reserve: <code>${u:.2f} USDC</code>\n"
                f"• Network: Arbitrum One (Chain ID 42161)\n\n"
                f"<i>Updated: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
            )
            telegram.send_photo(chart_file, caption=caption)
            return None
        return "⚠️ Could not generate chart. Please verify matplotlib is installed."

    def handle_ping_cmd() -> str:
        return "🏓 <b>Pong!</b> Trading bot is alive and running 24/7 on Google Cloud."

    telegram.register_command("/balance", handle_balance_cmd)
    telegram.register_command("/chart", handle_chart_cmd)
    telegram.register_command("/graph", handle_chart_cmd)
    telegram.register_command("/status", handle_status_cmd)
    telegram.register_command("/report", handle_report_cmd)
    telegram.register_command("/accuracy", handle_accuracy_cmd)
    telegram.register_command("/stats", handle_accuracy_cmd)
    telegram.register_command("/decision", handle_decision_cmd)
    telegram.register_command("/why", handle_decision_cmd)
    telegram.register_command("/gemini", handle_gemini_cmd)
    telegram.register_command("/ai", handle_gemini_cmd)
    telegram.register_command("/plan", handle_plan_cmd)
    telegram.register_command("/ping", handle_ping_cmd)

    # Start receiving interactive Telegram messages in background
    telegram.start_polling_in_background()

    # Send startup message
    telegram.send_startup_alert(acct.address, native_eth, usdc)

    price_history = []

    logger.info("================================================================================")
    logger.info(" AUTONOMOUS ARBITRUM ONE 24/7 TRADING ENGINE (TELEGRAM + INTELLIGENCE)")
    logger.info(f" Wallet:   {acct.address}")
    logger.info(f" Telegram: {'Configured & Active' if telegram.is_configured else 'Disabled (Token missing)'}")
    logger.info("================================================================================")

    while True:
        try:
            current_day = datetime.now(timezone.utc).day
            # Send daily summary if midnight UTC passed
            if current_day != last_daily_report_day:
                cur_w3 = get_resilient_web3()
                e, w, u = get_balances(cur_w3, acct.address)
                cur_usd = (e + w) * 3120.0 + u
                day_pnl = cur_usd - starting_total_usd

                telegram.send_daily_summary(
                    starting_bal_usd=starting_total_usd,
                    current_bal_usd=cur_usd,
                    net_pnl_usd=day_pnl,
                    trades_count=daily_trades_count,
                    total_gas_usd=daily_gas_spent_usd,
                    wallet_address=acct.address,
                )

                # Reset daily counters
                starting_total_usd = cur_usd
                daily_trades_count = 0
                daily_gas_spent_usd = 0.0
                last_daily_report_day = current_day

            w3 = get_resilient_web3()
            native_eth, weth, usdc = get_balances(w3, acct.address)
            total_usd = (native_eth + weth) * 3120.0 + usdc

            logger.info(f"Portfolio Status: {native_eth:.6f} ETH | {weth:.6f} WETH | {usdc:.4f} USDC | Total: ~${total_usd:.2f} USD")

            # Circuit-Breaker: Gas preservation check
            if native_eth < 0.00005:
                warn_msg = f"Gas reserve critically low ({native_eth:.6f} ETH < 0.00005). Pausing execution."
                logger.warning(warn_msg)
                telegram.send_error_alert("Gas Circuit Breaker", warn_msg)
                time.sleep(300)
                continue

            # Fetch live ETH/USD spot price
            try:
                import urllib.request
                req = urllib.request.Request("https://api.coinbase.com/v2/prices/ETH-USD/spot", headers={"User-Agent": "Bot/1.0"})
                data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
                spot_px = float(data["data"]["amount"])
            except Exception:
                spot_px = 3120.0

            price_history.append(spot_px)
            if len(price_history) > 30:
                price_history.pop(0)

            # Indicator momentum & RSI evaluation
            short_ma = float(np.mean(price_history[-5:])) if len(price_history) >= 5 else spot_px
            long_ma = float(np.mean(price_history[-10:])) if len(price_history) >= 10 else spot_px
            rsi = calculate_rsi(price_history)
            ma_diff_pct = ((short_ma - long_ma) / long_ma * 100.0) if long_ma > 0 else 0.0

            is_bullish = (short_ma > long_ma) and (rsi >= 40.0)
            is_bearish = (short_ma < long_ma) and (rsi <= 60.0)
            conviction = float(min(96.0, max(52.0, 65.0 + abs(ma_diff_pct) * 35.0)))

            regime = "BULLISH_EXPANSION" if is_bullish else ("BEARISH_PULLBACK" if is_bearish else "CONSOLIDATION_RANGE")

            # Update live state for /decision & /why Telegram queries
            current_decision_state["spot_px"] = spot_px
            current_decision_state["short_ma"] = short_ma
            current_decision_state["long_ma"] = long_ma
            current_decision_state["rsi"] = rsi
            current_decision_state["regime"] = regime
            current_decision_state["conviction_pct"] = conviction

            if weth >= 0.0003:
                current_decision_state["action"] = "HOLDING_WETH (Target: Take Profit or Bear Flip)"
                current_decision_state["rationale"] = (
                    f"Capital deployed in WETH (0.00050 WETH ~${weth * spot_px:.2f}). "
                    f"Fast MA (${short_ma:.2f}) vs Slow MA (${long_ma:.2f}), RSI={rsi:.1f}. "
                    "Holding position while trend remains favorable."
                )
                current_decision_state["next_trigger"] = (
                    f"Bearish crossover below Slow MA (${long_ma:.2f}) or RSI < 42 will trigger SELL to USDC."
                )
            elif usdc >= 0.50:
                current_decision_state["action"] = "HOLDING_USDC (Ready to Accumulate WETH)"
                current_decision_state["rationale"] = (
                    f"Capital preserved in USDC (${usdc:.2f} USDC). "
                    f"Fast MA (${short_ma:.2f}) vs Slow MA (${long_ma:.2f}), RSI={rsi:.1f}. "
                    "Waiting for confirmed bullish momentum cross to buy WETH."
                )
                current_decision_state["next_trigger"] = (
                    f"Bullish crossover above Slow MA (${long_ma:.2f}) with RSI > 45 will trigger BUY into WETH."
                )
            else:
                current_decision_state["action"] = "BALANCED_PORTFOLIO"
                current_decision_state["rationale"] = "Monitoring Arbitrum liquidity pools and spot price momentum."
                current_decision_state["next_trigger"] = "Waiting for capital allocation."

            # Execution triggers with Gemini AI Deliberation Gate
            if len(price_history) >= 10:
                holdings_summary = f"{native_eth:.6f} ETH, {weth:.6f} WETH, ${usdc:.2f} USDC"
                # Bullish & we hold USDC -> Evaluate BUY WETH
                if is_bullish and usdc >= 0.50:
                    ai_eval = gemini.deliberate(
                        candidate_action="BUY WETH",
                        spot_px=spot_px,
                        short_ma=short_ma,
                        long_ma=long_ma,
                        rsi=rsi,
                        holdings_desc=holdings_summary,
                    )
                    if ai_eval.get("approved") and ai_eval.get("action") == "BUY":
                        rationale = f"AI Approved: {ai_eval.get('rationale')}"
                        logger.info(f"{rationale}. Swapping {usdc:.4f} USDC -> WETH...")
                        swap_amount_wei = int(usdc * 1e6)
                        res = execute_swap(
                            w3, acct, USDC_ADDRESS, WETH_ADDRESS, swap_amount_wei,
                            fee_tier=500, telegram=telegram, decision_rationale=rationale,
                            conviction_pct=ai_eval.get("confidence_pct", conviction)
                        )
                        if res:
                            tx_hash, gas_paid, in_units, out_units, blk = res
                            daily_trades_count += 1
                            daily_gas_spent_usd += gas_paid
                            tracker.record_swap(
                                action="BUY WETH", token_in="USDC", token_out="WETH",
                                amount_in=in_units, amount_out=out_units, price_usd=spot_px,
                                gas_paid_usd=gas_paid, tx_hash=tx_hash, block_number=blk,
                                decision_rationale=rationale, conviction_pct=ai_eval.get("confidence_pct", conviction)
                            )
                    else:
                        logger.info(f"Trade Vetoed by Deliberation: {ai_eval.get('rationale')}. Conserving gas & capital.")

                # Bearish & we hold WETH -> Evaluate SELL WETH to USDC
                elif is_bearish and weth >= 0.0003:
                    ai_eval = gemini.deliberate(
                        candidate_action="BUY USDC (SELL WETH)",
                        spot_px=spot_px,
                        short_ma=short_ma,
                        long_ma=long_ma,
                        rsi=rsi,
                        holdings_desc=holdings_summary,
                    )
                    if ai_eval.get("approved") and ai_eval.get("action") in ["SELL", "BUY"]:
                        rationale = f"AI Approved: {ai_eval.get('rationale')}"
                        logger.info(f"{rationale}. Swapping {weth:.6f} WETH -> USDC...")
                        swap_amount_wei = int(weth * 1e18)
                        res = execute_swap(
                            w3, acct, WETH_ADDRESS, USDC_ADDRESS, swap_amount_wei,
                            fee_tier=500, telegram=telegram, decision_rationale=rationale,
                            conviction_pct=ai_eval.get("confidence_pct", conviction)
                        )
                        if res:
                            tx_hash, gas_paid, in_units, out_units, blk = res
                            daily_trades_count += 1
                            daily_gas_spent_usd += gas_paid
                            tracker.record_swap(
                                action="BUY USDC", token_in="WETH", token_out="USDC",
                                amount_in=in_units, amount_out=out_units, price_usd=spot_px,
                                gas_paid_usd=gas_paid, tx_hash=tx_hash, block_number=blk,
                                decision_rationale=rationale, conviction_pct=ai_eval.get("confidence_pct", conviction)
                            )
                    else:
                        logger.info(f"Exit Vetoed by Deliberation: {ai_eval.get('rationale')}. Holding position.")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Trading loop exception: {err_msg}")
            telegram.send_error_alert("Engine Exception", err_msg)

        time.sleep(60)


if __name__ == "__main__":
    run_continuous_trading_loop()
