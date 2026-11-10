"""
Bridge ETH from Ethereum Mainnet (L1) to Arbitrum One (L2).
Calls the official Arbitrum One Delayed Inbox contract `depositEth()` on Mainnet,
securing ultra-low gas fee trading on L2.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from eth_account import Account
from web3 import Web3

ENV_PATH = Path(".env")
MAINNET_RPC = "https://ethereum-rpc.publicnode.com"
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
ARBITRUM_INBOX = Web3.to_checksum_address("0x4Dbd4fc535ac27206064B68FfCf827b0A60BAB3f")


def get_private_key() -> str:
    key = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TRADING_HOT_WALLET_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not key or len(key) < 64:
        raise ValueError("TRADING_HOT_WALLET_KEY not found in .env")
    return key if key.startswith("0x") else "0x" + key


def main():
    private_key = get_private_key()
    acct = Account.from_key(private_key)
    sender = acct.address

    w3_l1 = Web3(Web3.HTTPProvider(MAINNET_RPC))
    if not w3_l1.is_connected():
        print("Error: Could not connect to Ethereum Mainnet RPC.")
        sys.exit(1)

    balance_wei = w3_l1.eth.get_balance(sender)
    balance_eth = balance_wei / 1e18
    print(f"[*] Wallet:           {sender}")
    print(f"[*] L1 Balance:       {balance_eth:.6f} ETH (${balance_eth * 3120.0:.2f} USD)")

    if balance_wei < 0.0003 * 1e18:
        print("Error: Insufficient balance to cover gas and deposit.")
        sys.exit(1)

    # Fetch gas details
    base_fee = w3_l1.eth.get_block("latest").get("baseFeePerGas", 600_000_000)
    priority_fee = int(0.05 * 1e9)  # 0.05 Gwei priority fee
    max_fee = int(base_fee * 1.35) + priority_fee
    gas_limit = 105000  # depositEth uses ~93,000 gas

    max_gas_cost_wei = gas_limit * max_fee
    # Reserve a safety cushion of 0.00001 ETH
    safety_cushion_wei = int(0.00001 * 1e18)

    deposit_wei = balance_wei - max_gas_cost_wei - safety_cushion_wei
    if deposit_wei <= 0:
        print("Error: Gas cost exceeds wallet balance.")
        sys.exit(1)

    deposit_eth = deposit_wei / 1e18
    gas_cost_eth = max_gas_cost_wei / 1e18

    print(f"[*] Deposit Amount:   {deposit_eth:.6f} ETH (${deposit_eth * 3120.0:.2f} USD)")
    print(f"[*] Max Gas Cost:     {gas_cost_eth:.6f} ETH (${gas_cost_eth * 3120.0:.2f} USD)")
    print(f"[*] Gas Price:        {max_fee / 1e9:.3f} Gwei")
    print(f"[*] Target Bridge:    Arbitrum One Inbox ({ARBITRUM_INBOX})")

    # Construct transaction
    nonce = w3_l1.eth.get_transaction_count(sender, "pending")
    tx = {
        "chainId": 1,
        "nonce": nonce,
        "to": ARBITRUM_INBOX,
        "value": deposit_wei,
        "data": "0x439370b1",  # depositEth()
        "gas": gas_limit,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee,
        "type": 2,
    }

    print("\n[*] Signing and broadcasting bridge transaction to Ethereum Mainnet...")
    signed = acct.sign_transaction(tx)
    tx_hash = w3_l1.eth.send_raw_transaction(signed.raw_transaction).hex()
    tx_hash_0x = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash

    print("\n" + "=" * 80)
    print(" L1 -> L2 ARBITRUM BRIDGE TRANSACTION BROADCAST!")
    print("=" * 80)
    print(f" Transaction Hash:   {tx_hash_0x}")
    print(f" Etherscan URL:      https://etherscan.io/tx/{tx_hash_0x}")
    print("=" * 80)

    # Wait for L1 confirmation
    print("[*] Waiting for Ethereum Mainnet block confirmation...")
    receipt = w3_l1.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        print(f"[+] Confirmed in L1 Block: {receipt.blockNumber} (Gas Used: {receipt.gasUsed})")
        print(f"[+] Actual Gas Cost:       {(receipt.gasUsed * receipt.effectiveGasPrice) / 1e18:.6f} ETH")
        print("\n[+] The Arbitrum Bridge sequencer is processing your deposit.")
        print(f"[+] Funds will be credited to {sender} on Arbitrum One in ~10-12 minutes.")
        print(f"[+] Monitor on Arbiscan: https://arbiscan.io/address/{sender}")
    else:
        print(f"[-] Transaction reverted on L1! Check: https://etherscan.io/tx/{tx_hash_0x}")
        sys.exit(1)


if __name__ == "__main__":
    main()
