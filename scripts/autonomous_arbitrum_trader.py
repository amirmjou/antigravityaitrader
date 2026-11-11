"""
Autonomous Arbitrum One On-Chain Trading Engine — M-Quant Cross-Asset Edition.
Continuous 24/7 Hardened Execution Daemon on Arbitrum One (Chain ID 42161).
Executes multi-asset rotation across WBTC, WETH, ARB, LINK, and Native USDC on Uniswap v3
using:
- Layer A: WBTC/WETH Log-Ratio Momentum Oscillator (RMO) & Rolling Z-Score Bounds
- Layer B: Multi-Factor Macro Regime Filter (M_t) & Sortino-Adjusted Altcoin Rotation
- Layer C: Inverse Volatility, Fractional Kelly, Chandelier Trailing Stops,
           3-Tier Drawdown Circuit Breakers, QuoterV2 Slippage Checks & Cost-Aware Drift Rebalancing.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from eth_account import Account
from web3 import Web3

from core.ai.gemini_deliberator import GeminiDeliberator
from core.analytics.accuracy_tracker import AccuracyTracker
from core.notifications.telegram_notifier import TelegramNotifier
from core.visualization.chart_generator import generate_balance_chart
from crypto_pipeline.ingestion.arbitrum_market_data import (
    build_token_market_snapshot,
    fetch_closed_klines,
    fetch_fear_and_greed_index,
    quote_uniswap_v3_swap,
)
from crypto_pipeline.strategies.quant_rotation import MQuantRotationStrategy, RiskAndDriftAllocator
from execution.contracts.quant_architecture import (
    ARBITRUM_TOKENS,
    CANONICAL_ARBITRUM_QUOTER_V2,
    CANONICAL_ARBITRUM_SWAP_ROUTER_02,
    CircuitBreakerStatus,
    RebalanceOrder,
    TokenMarketData,
)
from execution.routers.dex_router import MultiDEXRouter

# Configure structured logging for Google Cloud Logging / Stackdriver
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("arbitrum-trader")

ENV_PATH = Path(".env")
SYSTEMD_ENV = Path("/etc/tradingbot/tradingbot.env")

ARBITRUM_RPC_URLS = [
    "https://arb1.arbitrum.io/rpc",
    "https://arbitrum-one.publicnode.com",
    "https://1rpc.io/arb",
    "https://arbitrum.llamarpc.com",
]

UNISWAP_V3_ROUTER = Web3.to_checksum_address(CANONICAL_ARBITRUM_SWAP_ROUTER_02)
QUOTER_V2_ADDRESS = Web3.to_checksum_address(CANONICAL_ARBITRUM_QUOTER_V2)
WETH_ADDRESS = Web3.to_checksum_address(ARBITRUM_TOKENS["WETH"].address)
USDC_ADDRESS = Web3.to_checksum_address(ARBITRUM_TOKENS["USDC"].address)
WBTC_ADDRESS = Web3.to_checksum_address(ARBITRUM_TOKENS["WBTC"].address)
ARB_ADDRESS = Web3.to_checksum_address(ARBITRUM_TOKENS["ARB"].address)
LINK_ADDRESS = Web3.to_checksum_address(ARBITRUM_TOKENS["LINK"].address)

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
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "bytes", "name": "path", "type": "bytes"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                ],
                "internalType": "struct IV3SwapRouter.ExactInputParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInput",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
]


def load_secret_key() -> str:
    key = os.environ.get("TRADING_HOT_WALLET_KEY")
    if not key:
        for p in (ENV_PATH, SYSTEMD_ENV):
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
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 8}))
            if w3.is_connected():
                return w3
        except Exception:
            continue
    raise ConnectionError("Failed to connect to any Arbitrum One RPC node.")


def get_balances(w3: Web3, address: str) -> Tuple[float, float, float]:
    """Backward-compatible helper returning (native_eth, weth, usdc)."""
    multi = get_multi_asset_balances(w3, address)
    return multi["ETH"], multi["WETH"], multi["USDC"]


def get_multi_asset_balances(w3: Web3, address: str) -> Dict[str, float]:
    """Fetch on-chain balances for ETH (gas) and all 5 M-Quant target ERC-20 tokens."""
    balances: Dict[str, float] = {"ETH": w3.eth.get_balance(address) / 1e18}
    for sym, spec in ARBITRUM_TOKENS.items():
        c = w3.eth.contract(address=Web3.to_checksum_address(spec.address), abi=ERC20_ABI)
        raw = c.functions.balanceOf(address).call()
        balances[sym] = raw / (10 ** spec.decimals)
    return balances


def _ensure_allowance(w3: Web3, acct: Any, token_addr: str, amount_in_wei: int, symbol: str) -> int:
    address = acct.address
    token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)
    allowance = token_contract.functions.allowance(address, UNISWAP_V3_ROUTER).call()
    nonce = w3.eth.get_transaction_count(address, "pending")
    if allowance < amount_in_wei:
        gas_price = w3.eth.gas_price
        logger.info(f"Approving SwapRouter02 for {symbol}...")
        approve_tx = token_contract.functions.approve(UNISWAP_V3_ROUTER, 2**256 - 1).build_transaction({
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
    return nonce


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
    route_addresses: Optional[List[str]] = None,
    fee_tiers_path: Optional[List[int]] = None,
    eth_price_usd: float = 3120.0,
) -> Optional[Tuple[str, float, float, float, int]]:
    """
    Execute a single-hop or multi-hop Uniswap v3 swap on Arbitrum One with live QuoterV2 slippage protection.
    """
    address = acct.address
    router = w3.eth.contract(address=UNISWAP_V3_ROUTER, abi=ROUTER_ABI)

    sym_in = next((s for s, sp in ARBITRUM_TOKENS.items() if sp.address.lower() == token_in.lower()), "TOKEN_IN")
    sym_out = next((s for s, sp in ARBITRUM_TOKENS.items() if sp.address.lower() == token_out.lower()), "TOKEN_OUT")
    dec_in = ARBITRUM_TOKENS[sym_in].decimals if sym_in in ARBITRUM_TOKENS else 18
    dec_out = ARBITRUM_TOKENS[sym_out].decimals if sym_out in ARBITRUM_TOKENS else 18
    in_units = amount_in_wei / (10 ** dec_in)

    addrs = route_addresses if route_addresses else [token_in, token_out]
    fees = fee_tiers_path if fee_tiers_path else [fee_tier]

    # Live QuoterV2 minimum output calculation (50 bps tolerance; 75 bps on multi-hop)
    min_out_wei = 0
    try:
        quoted_out, _ = quote_uniswap_v3_swap(w3, addrs, fees, amount_in_wei, QUOTER_V2_ADDRESS)
        slippage_tol = 0.0075 if len(addrs) > 2 else 0.0050
        min_out_wei = max(1, int(quoted_out * (1.0 - slippage_tol)))
    except Exception as qe:
        logger.warning(f"QuoterV2 pre-quote fallback for {sym_in}->{sym_out}: {qe}")

    before_balances = get_multi_asset_balances(w3, address)
    nonce = _ensure_allowance(w3, acct, token_in, amount_in_wei, sym_in)
    gas_price = w3.eth.gas_price

    if len(addrs) <= 2:
        params = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            int(fees[0]),
            address,
            int(amount_in_wei),
            int(min_out_wei),
            0,
        )
        fn_call = router.functions.exactInputSingle(params)
        gas_lim = 300000
    else:
        path_bytes = MultiDEXRouter.encode_v3_path(addrs, fees)
        fn_call = router.functions.exactInput((path_bytes, address, int(amount_in_wei), int(min_out_wei)))
        gas_lim = 450000

    swap_tx = fn_call.build_transaction({
        "from": address,
        "nonce": nonce,
        "gas": gas_lim,
        "gasPrice": int(gas_price * 1.25),
        "chainId": 42161,
    })

    signed = acct.sign_transaction(swap_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    tx_hash_0x = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash

    logger.info(f"Swap broadcast ({sym_in} -> {sym_out}): https://arbiscan.io/tx/{tx_hash_0x}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.status == 1:
        gas_paid_eth = (receipt.gasUsed * receipt.effectiveGasPrice) / 1e18
        gas_paid_usd = gas_paid_eth * eth_price_usd
        after_balances = get_multi_asset_balances(w3, address)
        out_delta = max(0.0, after_balances.get(sym_out, 0.0) - before_balances.get(sym_out, 0.0))
        out_units = out_delta if out_delta > 0 else after_balances.get(sym_out, 0.0)
        logger.info(f"SWAP CONFIRMED: Block {receipt.blockNumber} | +{out_units:.6f} {sym_out} | Gas Paid: ${gas_paid_usd:.4f}")

        if telegram and telegram.is_configured:
            telegram.send_trade_receipt(
                action=f"ROTATE {sym_in} ➔ {sym_out}",
                token_in_name=sym_in,
                token_out_name=sym_out,
                amount_in=in_units,
                amount_out=out_units,
                tx_hash=tx_hash_0x,
                gas_paid_usd=gas_paid_usd,
                block_number=receipt.blockNumber,
                decision_rationale=decision_rationale,
                conviction_pct=conviction_pct,
            )

        return tx_hash_0x, gas_paid_usd, in_units, out_units, receipt.blockNumber

    err_msg = f"Swap transaction reverted on Arbitrum ({sym_in} -> {sym_out}): https://arbiscan.io/tx/{tx_hash_0x}"
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
    return float(np.clip(100.0 - (100.0 / (1.0 + rs)), 0.0, 100.0))


def _compute_portfolio_usd(balances: Dict[str, float], snapshot: Dict[str, TokenMarketData]) -> float:
    eth_px = snapshot["WETH"].price_usd if "WETH" in snapshot else 3120.0
    tot = balances.get("ETH", 0.0) * eth_px
    for sym in ARBITRUM_TOKENS:
        px = snapshot[sym].price_usd if sym in snapshot else (1.0 if sym == "USDC" else 0.0)
        tot += balances.get(sym, 0.0) * px
    return tot


def run_continuous_trading_loop():
    key = load_secret_key()
    acct = Account.from_key(key)
    w3 = get_resilient_web3()

    telegram = TelegramNotifier()
    tracker = AccuracyTracker()
    gemini = GeminiDeliberator()

    # Load configurable rebalance dust threshold (supports micro-capital testing or institutional $50 floor)
    balances = get_multi_asset_balances(w3, acct.address)
    daily_candles_init = {sym: fetch_closed_klines(sym, interval="1d", limit=210) for sym in ("WBTC", "WETH", "ARB", "LINK")}
    snapshot = build_token_market_snapshot(daily_candles_init)
    starting_total_usd = _compute_portfolio_usd(balances, snapshot)

    default_min_trade = 50.0 if starting_total_usd >= 100.0 else 0.50
    min_trade_usd = float(os.environ.get("MQUANT_MIN_TRADE_USD", str(default_min_trade)))
    rebalance_cooldown_sec = int(os.environ.get("MQUANT_REBALANCE_COOLDOWN_SEC", "900"))  # 15 min anti-churn gate

    strategy = MQuantRotationStrategy(
        min_trade_usd=min_trade_usd,
        max_trade_usd=250.0,
        asset_drift_max=0.05,
        portfolio_drift_max=0.08,
    )
    # Allow cost ratio up to 1.5% under Guardrail L4 for micro-capital portfolios
    if starting_total_usd < 100.0:
        strategy.allocator.max_cost_ratio = 0.015

    daily_trades_count = 0
    daily_gas_spent_usd = 0.0
    last_daily_report_day = datetime.now(timezone.utc).day
    day_open_usd = starting_total_usd
    high_water_mark_usd = starting_total_usd
    last_rebalance_ts = 0.0
    last_market_fetch_ts = 0.0
    cached_4h: Dict[str, List[float]] = {}
    cached_daily: Dict[str, List[float]] = {}
    cached_fng = 50

    current_decision_state: Dict[str, Any] = {
        "spot_px": snapshot["WETH"].price_usd,
        "wbtc_px": snapshot["WBTC"].price_usd,
        "short_ma": snapshot["WETH"].price_usd,
        "long_ma": snapshot["WETH"].price_usd,
        "rsi": 50.0,
        "regime": "NEUTRAL_STARTUP",
        "macro_score": 0.50,
        "fng": 50,
        "rmo_score": 0.0,
        "rmo_z": 0.0,
        "conviction_pct": 75.0,
        "target_weights": {"WBTC": 0.0, "WETH": 0.0, "ARB": 0.0, "LINK": 0.0, "USDC": 1.0},
        "action": "INITIALIZING_MQUANT",
        "rationale": "Bootstrapping M-Quant 5-asset cross-rotation engine.",
        "next_trigger": "Awaiting closed-bar 4h/1d regime evaluation.",
    }

    # --- Interactive Telegram Command Handlers ---
    def handle_balance_cmd() -> str:
        cur_w3 = get_resilient_web3()
        b = get_multi_asset_balances(cur_w3, acct.address)
        tot = _compute_portfolio_usd(b, snapshot)
        return (
            "💰 <b>Current Arbitrum M-Quant Portfolio:</b>\n\n"
            f"• Gas Reserve (ETH): <code>{b['ETH']:.6f} ETH</code>\n"
            f"• WBTC: <code>{b['WBTC']:.6f}</code> (~${b['WBTC'] * snapshot['WBTC'].price_usd:.2f})\n"
            f"• WETH: <code>{b['WETH']:.6f}</code> (~${b['WETH'] * snapshot['WETH'].price_usd:.2f})\n"
            f"• ARB:  <code>{b['ARB']:.4f}</code> (~${b['ARB'] * snapshot['ARB'].price_usd:.2f})\n"
            f"• LINK: <code>{b['LINK']:.4f}</code> (~${b['LINK'] * snapshot['LINK'].price_usd:.2f})\n"
            f"• USDC: <code>${b['USDC']:.4f}</code>\n\n"
            f"💵 <b>Total Valuation:</b> <b>${tot:.2f} USD</b>\n"
            f"🔗 <a href='https://arbiscan.io/address/{acct.address}'>Arbiscan Explorer</a>"
        )

    def handle_strategy_cmd() -> str:
        tw = current_decision_state.get("target_weights", {})
        return (
            "🧭 <b>M-Quant Cross-Asset Strategy State:</b>\n\n"
            f"• Macro Regime: <b>{current_decision_state.get('regime')}</b> "
            f"(Score <code>M_t={current_decision_state.get('macro_score', 0):.2f}</code>, F&G=<code>{current_decision_state.get('fng', 50)}</code>)\n"
            f"• WBTC/WETH RMO: <code>S={current_decision_state.get('rmo_score', 0):+.2f}</code> | "
            f"<code>Z={current_decision_state.get('rmo_z', 0):+.2f}</code>\n"
            f"• Target Allocation:\n"
            f"  - WBTC: <code>{tw.get('WBTC', 0)*100:.1f}%</code> | WETH: <code>{tw.get('WETH', 0)*100:.1f}%</code>\n"
            f"  - ARB:  <code>{tw.get('ARB', 0)*100:.1f}%</code> | LINK: <code>{tw.get('LINK', 0)*100:.1f}%</code>\n"
            f"  - USDC: <code>{tw.get('USDC', 0)*100:.1f}%</code>\n"
            f"• Dust Floor: <code>${min_trade_usd:.2f}</code> | Cooldown: <code>{rebalance_cooldown_sec//60}m</code>"
        )

    def handle_status_cmd() -> str:
        cur_w3 = get_resilient_web3()
        blk = cur_w3.eth.block_number
        gwei = cur_w3.eth.gas_price / 1e9
        return (
            "🟢 <b>System Status: M-QUANT ONLINE</b>\n\n"
            f"• Arbitrum Block: <code>{blk}</code>\n"
            f"• Gas Price: <code>{gwei:.3f} Gwei</code>\n"
            f"• Swaps Today: <b>{daily_trades_count}</b> | Gas: <code>${daily_gas_spent_usd:.4f}</code>"
        )

    def handle_report_cmd() -> str:
        cur_w3 = get_resilient_web3()
        b = get_multi_asset_balances(cur_w3, acct.address)
        cur_tot = _compute_portfolio_usd(b, snapshot)
        pnl = cur_tot - starting_total_usd
        return (
            "📊 <b>Today's M-Quant Performance Report:</b>\n\n"
            f"• Starting Balance: <code>${starting_total_usd:.2f} USD</code>\n"
            f"• Current Balance: <b>${cur_tot:.2f} USD</b>\n"
            f"• Net PnL: <b>{'+' if pnl >= 0 else ''}${pnl:.2f} USD</b>\n"
            f"• Completed Swaps: {daily_trades_count} | Gas Paid: <code>${daily_gas_spent_usd:.4f}</code>"
        )

    def handle_chart_cmd() -> Optional[str]:
        cur_w3 = get_resilient_web3()
        b = get_multi_asset_balances(cur_w3, acct.address)
        tot = _compute_portfolio_usd(b, snapshot)
        chart_file = generate_balance_chart(
            current_eth=b["ETH"],
            current_weth=b["WETH"],
            current_usdc=b["USDC"],
            eth_price=snapshot["WETH"].price_usd,
        )
        if chart_file and os.path.exists(chart_file):
            caption = (
                f"📊 <b>Arbitrum M-Quant Portfolio Chart</b>\n"
                f"• Total Valuation: <b>${tot:.2f} USD</b>\n"
                f"• Regime: {current_decision_state.get('regime')} | Updated: {time.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            telegram.send_photo(chart_file, caption=caption)
            return None
        return "⚠️ Could not generate chart."

    def handle_gemini_cmd() -> str:
        b = get_multi_asset_balances(get_resilient_web3(), acct.address)
        holdings_str = (
            f"{b['ETH']:.6f} ETH, {b['WBTC']:.6f} WBTC, {b['WETH']:.6f} WETH, "
            f"{b['ARB']:.2f} ARB, {b['LINK']:.2f} LINK, ${b['USDC']:.2f} USDC"
        )
        return gemini.format_market_intelligence(
            spot_px=snapshot["WETH"].price_usd,
            short_ma=current_decision_state.get("short_ma", 3120.0),
            long_ma=current_decision_state.get("long_ma", 3120.0),
            rsi=current_decision_state.get("rsi", 50.0),
            holdings_desc=holdings_str,
        )

    telegram.register_command("/balance", handle_balance_cmd)
    telegram.register_command("/strategy", handle_strategy_cmd)
    telegram.register_command("/regime", handle_strategy_cmd)
    telegram.register_command("/chart", handle_chart_cmd)
    telegram.register_command("/graph", handle_chart_cmd)
    telegram.register_command("/status", handle_status_cmd)
    telegram.register_command("/report", handle_report_cmd)
    telegram.register_command("/accuracy", tracker.format_accuracy_report)
    telegram.register_command("/stats", tracker.format_accuracy_report)
    telegram.register_command("/decision", lambda: tracker.format_decision_report(current_decision_state))
    telegram.register_command("/why", lambda: tracker.format_decision_report(current_decision_state))
    telegram.register_command("/gemini", handle_gemini_cmd)
    telegram.register_command("/ai", handle_gemini_cmd)
    telegram.register_command("/plan", tracker.format_plan_report)
    telegram.register_command("/ping", lambda: "🏓 <b>Pong!</b> M-Quant 5-Asset Engine active on Arbitrum One.")

    telegram.start_polling_in_background()
    telegram.send_startup_alert(acct.address, balances["ETH"], balances["USDC"])

    logger.info("================================================================================")
    logger.info(" AUTONOMOUS ARBITRUM ONE M-QUANT CROSS-ASSET ENGINE (WBTC/WETH/ARB/LINK/USDC)")
    logger.info(f" Wallet:   {acct.address} | Dust Floor: ${min_trade_usd:.2f} | Cooldown: {rebalance_cooldown_sec}s")
    logger.info(f" Telegram: {'Configured & Active' if telegram.is_configured else 'Disabled'}")
    logger.info("================================================================================")

    while True:
        try:
            now_ts = time.time()
            current_day = datetime.now(timezone.utc).day

            # Daily summary at UTC rollover
            if current_day != last_daily_report_day:
                cur_b = get_multi_asset_balances(get_resilient_web3(), acct.address)
                cur_usd = _compute_portfolio_usd(cur_b, snapshot)
                telegram.send_daily_summary(
                    starting_bal_usd=day_open_usd,
                    current_bal_usd=cur_usd,
                    net_pnl_usd=cur_usd - day_open_usd,
                    trades_count=daily_trades_count,
                    total_gas_usd=daily_gas_spent_usd,
                    wallet_address=acct.address,
                )
                day_open_usd = cur_usd
                daily_trades_count = 0
                daily_gas_spent_usd = 0.0
                last_daily_report_day = current_day

            w3 = get_resilient_web3()
            balances = get_multi_asset_balances(w3, acct.address)

            # Circuit Breaker: Gas reserve preservation
            if balances["ETH"] < 0.00005:
                warn_msg = f"Gas reserve critically low ({balances['ETH']:.6f} ETH < 0.00005). Pausing swaps."
                logger.warning(warn_msg)
                telegram.send_error_alert("Gas Circuit Breaker", warn_msg)
                time.sleep(300)
                continue

            # Refresh closed OHLCV feeds every 5 minutes (4h/1d bars do not change every 60s)
            if (now_ts - last_market_fetch_ts) >= 300.0 or not cached_daily:
                daily_raw = {sym: fetch_closed_klines(sym, interval="1d", limit=210) for sym in ("WBTC", "WETH", "ARB", "LINK")}
                cached_daily = {sym: [c[4] for c in candles] for sym, candles in daily_raw.items()}
                h4_b = fetch_closed_klines("WBTC", interval="4h", limit=200)
                h4_e = fetch_closed_klines("WETH", interval="4h", limit=200)
                cached_4h = {
                    "WBTC": [c[4] for c in h4_b],
                    "WETH": [c[4] for c in h4_e],
                }
                snapshot = build_token_market_snapshot(daily_raw)
                cached_fng = fetch_fear_and_greed_index()
                last_market_fetch_ts = now_ts

            total_usd = _compute_portfolio_usd(balances, snapshot)
            high_water_mark_usd = max(high_water_mark_usd, total_usd)
            daily_dd_pct = ((day_open_usd - total_usd) / day_open_usd * 100.0) if day_open_usd > 0 else 0.0
            cum_dd_pct = ((high_water_mark_usd - total_usd) / high_water_mark_usd * 100.0) if high_water_mark_usd > 0 else 0.0

            gas_price_gwei = w3.eth.gas_price / 1e9
            est_gas_usd = 145000 * gas_price_gwei * 1e-9 * snapshot["WETH"].price_usd

            # Run 3-layer M-Quant Cross-Asset Strategy Evaluation
            decision, macro_state, ratio_sig, _ = strategy.evaluate(
                wbtc_4h_closes=cached_4h["WBTC"],
                weth_4h_closes=cached_4h["WETH"],
                daily_closes=cached_daily,
                fear_and_greed=cached_fng,
                token_snapshot=snapshot,
                current_units=balances,
                recipient_address=acct.address,
                daily_dd_pct=max(0.0, daily_dd_pct),
                cum_dd_pct=max(0.0, cum_dd_pct),
                gas_cost_usd=est_gas_usd,
                last_rebalance_age_days=(now_ts - last_rebalance_ts) / 86400.0 if last_rebalance_ts > 0 else 0.0,
            )

            weth_closes_4h = cached_4h["WETH"]
            current_decision_state.update({
                "spot_px": snapshot["WETH"].price_usd,
                "wbtc_px": snapshot["WBTC"].price_usd,
                "short_ma": float(np.mean(weth_closes_4h[-5:])),
                "long_ma": float(np.mean(weth_closes_4h[-20:])),
                "rsi": calculate_rsi(weth_closes_4h[-20:]),
                "regime": macro_state.regime.value,
                "macro_score": macro_state.macro_score,
                "fng": cached_fng,
                "rmo_score": ratio_sig.raw_score,
                "rmo_z": ratio_sig.z_score,
                "conviction_pct": round(macro_state.confidence * 100.0, 1),
                "target_weights": decision.target_weights,
                "action": "REBALANCE_TRIGGERED" if decision.rebalance_required else f"HOLDING ({macro_state.regime.value})",
                "rationale": decision.rationale,
                "next_trigger": (
                    f"Evaluating {len(decision.orders)} drift orders"
                    if decision.rebalance_required
                    else "Waiting for >=5% single-asset or >=8% portfolio drift vs targets."
                ),
            })

            logger.info(
                f"M-Quant Status: ${total_usd:.2f} USD | ETH={balances['ETH']:.6f} "
                f"WBTC={balances['WBTC']:.6f} WETH={balances['WETH']:.6f} ARB={balances['ARB']:.2f} "
                f"LINK={balances['LINK']:.2f} USDC=${balances['USDC']:.2f} | {macro_state.regime.value} (M={macro_state.macro_score:.2f})"
            )

            cooldown_ok = (now_ts - last_rebalance_ts) >= rebalance_cooldown_sec
            is_emergency = decision.circuit_breaker_status == CircuitBreakerStatus.TIER3_LOCKED_DOWN

            if decision.rebalance_required and decision.orders and (cooldown_ok or is_emergency):
                for order in decision.orders:
                    # Gemini Deliberation Gate (optional advisory if API key active; falls back cleanly)
                    holdings_desc = (
                        f"{balances['ETH']:.6f} ETH, {balances['WBTC']:.6f} WBTC, {balances['WETH']:.6f} WETH, "
                        f"{balances['ARB']:.2f} ARB, {balances['LINK']:.2f} LINK, ${balances['USDC']:.2f} USDC"
                    )
                    ai_eval = gemini.deliberate(
                        candidate_action=f"BUY {order.symbol_out}" if order.symbol_out != "USDC" else f"SELL {order.symbol_in}",
                        spot_px=snapshot[order.symbol_out if order.symbol_out != "USDC" else order.symbol_in].price_usd,
                        short_ma=current_decision_state["short_ma"],
                        long_ma=current_decision_state["long_ma"],
                        rsi=current_decision_state["rsi"],
                        holdings_desc=holdings_desc,
                    )
                    if not ai_eval.get("approved") and not is_emergency:
                        logger.info(f"Rebalance order vetoed by Gemini/Guardrail: {ai_eval.get('rationale')}")
                        continue

                    logger.info(
                        f"Executing M-Quant Rebalance: {' -> '.join(order.route_symbols)} "
                        f"(${order.trade_notional_usd:.2f} USD | Fee tier={order.fee_tiers_path})"
                    )
                    res = execute_swap(
                        w3=w3,
                        acct=acct,
                        token_in=order.token_in,
                        token_out=order.token_out,
                        amount_in_wei=order.amount_in_wei,
                        fee_tier=order.fee_tier,
                        telegram=telegram,
                        decision_rationale=f"M-Quant: {decision.rationale}",
                        conviction_pct=ai_eval.get("confidence_pct", macro_state.confidence * 100.0),
                        route_addresses=order.route_path,
                        fee_tiers_path=order.fee_tiers_path,
                        eth_price_usd=snapshot["WETH"].price_usd,
                    )
                    if res:
                        tx_hash, gas_paid, in_u, out_u, blk = res
                        daily_trades_count += 1
                        daily_gas_spent_usd += gas_paid
                        last_rebalance_ts = time.time()
                        tracker.record_swap(
                            action=f"{order.symbol_in}->{order.symbol_out}",
                            token_in=order.symbol_in,
                            token_out=order.symbol_out,
                            amount_in=in_u,
                            amount_out=out_u,
                            price_usd=snapshot[order.symbol_out if order.symbol_out != "USDC" else order.symbol_in].price_usd,
                            gas_paid_usd=gas_paid,
                            tx_hash=tx_hash,
                            block_number=blk,
                            decision_rationale=decision.rationale,
                            conviction_pct=ai_eval.get("confidence_pct", macro_state.confidence * 100.0),
                        )
                    time.sleep(3)

        except Exception as e:
            err_msg = str(e)
            logger.error(f"M-Quant loop exception: {err_msg}")
            telegram.send_error_alert("Engine Exception", err_msg)

        time.sleep(60)


if __name__ == "__main__":
    run_continuous_trading_loop()
