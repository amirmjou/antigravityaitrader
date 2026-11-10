"""
Setup Dedicated On-Chain Trading Wallet.
Generates an isolated EVM account for automated trading on Arbitrum One / Base,
saves the private key strictly to .env, and displays the public address.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from eth_account import Account
from web3 import Web3

ENV_PATH = Path(".env")
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
BASE_RPC = "https://mainnet.base.org"


def main():
    # Enable Mnemonic/HD features if needed, standard account generation
    Account.enable_unaudited_hdwallet_features()

    # Check if a hot wallet key already exists in .env
    existing_key = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TRADING_HOT_WALLET_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and len(val) >= 64:
                    existing_key = val
                    break

    if existing_key:
        acct = Account.from_key(existing_key)
        created = False
    else:
        acct = Account.create()
        created = True
        key_hex = acct.key.hex()
        if not key_hex.startswith("0x"):
            key_hex = "0x" + key_hex

        # Append or update .env safely
        env_lines = []
        if ENV_PATH.exists():
            env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

        updated = False
        new_lines = []
        for line in env_lines:
            if line.strip().startswith("TRADING_HOT_WALLET_KEY="):
                new_lines.append(f"TRADING_HOT_WALLET_KEY={key_hex}")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"TRADING_HOT_WALLET_KEY={key_hex}")

        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    address = acct.address

    # Query live balances via public RPCs
    arb_bal = 0.0
    base_bal = 0.0
    try:
        w3_arb = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
        if w3_arb.is_connected():
            arb_bal = w3_arb.eth.get_balance(address) / 1e18
    except Exception as e:
        pass

    try:
        w3_base = Web3(Web3.HTTPProvider(BASE_RPC))
        if w3_base.is_connected():
            base_bal = w3_base.eth.get_balance(address) / 1e18
    except Exception as e:
        pass

    print("================================================================================")
    print(" DEDICATED ON-CHAIN TRADING WALLET INITIALIZATION")
    print("================================================================================")
    print(f" Status:             {'NEW WALLET GENERATED' if created else 'EXISTING WALLET LOADED'}")
    print(f" Public Address:     {address}")
    print(f" Private Key:        Stored securely in .env (TRADING_HOT_WALLET_KEY)")
    print("--------------------------------------------------------------------------------")
    print(f" Arbitrum One (42161) Balance: {arb_bal:.6f} ETH (${arb_bal * 3120.0:.2f} USD)")
    print(f" Base (8453) Balance:          {base_bal:.6f} ETH (${base_bal * 3120.0:.2f} USD)")
    print("================================================================================")
    print(" DEPOSIT INSTRUCTIONS:")
    print(" Send your 0.0012 ETH from your MetaMask wallet to the Public Address above")
    print(" on ARBITRUM ONE network (recommended for ultra-low gas: ~$0.015/swap).")
    print(" Arbiscan Explorer: https://arbiscan.io/address/" + address)
    print("================================================================================")


if __name__ == "__main__":
    main()
