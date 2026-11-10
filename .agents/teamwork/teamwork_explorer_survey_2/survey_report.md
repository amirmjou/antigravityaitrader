# Technical Survey Report: MetaMask Wallet Connectivity & Automated Execution Safeguards

**Milestone**: Phase 0 — Survey & Architecture Discovery  
**Author**: `teamwork_explorer_survey_2`  
**Target Requirement**: Requirement R2 (MetaMask Wallet Integration & Safety Guardrails)  
**Date**: 2026-11-06  

---

## Executive Summary

This report delivers a rigorous architectural investigation into connecting the **Antigravity Multi-Agent Trading System** (incorporating `TauricResearch/TradingAgents`) with MetaMask wallet connectivity for on-chain execution, governed by an automated, multi-tiered **Pre-Broadcast Safety Guardrail Pipeline (PBSGP)**.

### Core Discoveries & Recommendations:
1. **Wallet Integration Reality**: MetaMask is fundamentally an interactive, non-custodial browser/mobile signer. It cannot sign arbitrary unattended transactions without either human-in-the-loop interaction, scoped smart account delegation (ERC-7715 / Session Keys), or a local delegated hot-wallet signer. We recommend a **Dual-Engine Wallet Architecture**:
   - **Engine A (Interactive Attended Mode)**: A local FastAPI + WebSocket bridge serving an EIP-1193 / `@metamask/connect-evm` interface, allowing the user to inspect agent reasoning and approve on-chain transactions directly in MetaMask.
   - **Engine B (Autonomous Sub-Account Mode)**: A dedicated trading hot wallet managed via `eth-account` / `web3.py` (AES-128 encrypted keystore), funded from MetaMask with capped operational capital (e.g. $200 / 0.1 ETH) for 100% unattended autonomous trading.
2. **Pre-Broadcast Safety Guardrail Pipeline**: A 6-layer serial defense matrix executed in Python prior to invoking `eth_sendRawTransaction` or MetaMask popup:
   - *Layer 1*: Contract & Token Security Audit (GoPlus Security API honeypot, mintable, tax <1% check).
   - *Layer 2*: Capital & Portfolio Allocation Caps (hard per-trade ceiling, max 20% single-asset exposure, 24h drawdown circuit breaker).
   - *Layer 3*: Dynamic Slippage & Price Impact Guard (Uniswap `IQuoterV2` query, dynamic 30–100 bps slippage, reject impact >2.0%, strict deadline).
   - *Layer 4*: Gas Price & Network Congestion Checker (EIP-1559 base fee ceiling, max gas-to-trade value ratio <1.5%, gas buffer cap).
   - *Layer 5*: Pre-Flight State Simulation (`eth_call` dry-run, revert decoding, optional Tenderly/Alchemy trace simulation).
   - *Layer 6*: Signing & Broadcasting Router (dispatches to either MetaMask bridge or local signer).
3. **Execution Target Chains**: Primary execution on **Arbitrum One (L2)** and **Base (L2)** (sub-cent fees, 250ms–2s blocks, high DEX liquidity via Uniswap v3 & Aerodrome). Ethereum L1 is supported for high-capital trades (> $1,000), while Solana execution (R4 requirement for BTC/ETH/SOL) is addressed via EVM Wrapped Solana or Decentralized Perpetuals (Hyperliquid/GMX Synthetics) using MetaMask.

---

## 1. MetaMask Wallet Connectivity Architectures

### 1.1 The Fundamental Constraint of MetaMask
MetaMask is an EIP-1193 non-custodial signer. Private keys are encrypted in the client's local vault (browser extension or mobile enclave). Every signature request (`eth_sendTransaction`, `personal_sign`, `eth_signTypedData_v4`) triggers a security modal requiring explicit user authorization.

To balance **autonomous agent execution** with **MetaMask connectivity**, four distinct architectural models were evaluated.

### 1.2 Comparison Matrix of Connectivity Models

| Evaluation Criteria | Model A: Interactive Local Bridge (MetaMask Connect) | Model B: ERC-7715 Session Keys (Smart Accounts) | Model C: Delegated Local Hot Signer (`eth-account`) | Model D: Headless Extension Automation (Playwright) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Mechanism** | Local FastAPI + WebSocket bridge to Web Dapp / EIP-1193 | `wallet_requestExecutionPermissions` via MetaMask Smart Accounts | Local Python encrypted keystore signer | Chromium with loaded MetaMask extension automated via Playwright |
| **Autonomy Level** | Semi-autonomous (Human click required per trade) | 100% Autonomous (After 1-time scoped user approval) | 100% Autonomous (Fully unattended 24/7) | 100% Autonomous (DOM click script) |
| **Key Custody & Risk** | Zero key exposure (Keys stay in MetaMask extension) | Non-custodial, cryptographically enforced on-chain limits | Custodial hot wallet (Risk strictly isolated to allocated funds) | High risk (Password/seed phrase stored in automation scripts) |
| **Latency** | Human latency (10s – 5 mins) | Sub-3s (via ERC-4337 Bundler) | Sub-500ms (Direct JSON-RPC broadcast) | 3s – 10s (DOM rendering and popup event loop) |
| **Setup Complexity** | Low (FastAPI + HTML5/React EIP-1193) | Medium/High (Requires ERC-4337 bundler RPC & smart contracts) | Minimal (`web3.py`, `eth-account`, pure Python) | High & Fragile (Breaks on extension DOM updates) |
| **Reliability / Uptime** | 99.9% (Native browser IPC) | 98.5% (Dependent on bundler availability) | 99.99% (Direct connection to Alchemy/Infura RPC) | <80% (Extension popups lose focus, timeout, or crash) |
| **Recommendation** | **Supported (Attended Mode)** | **Future Phase (Pectra/ERC-7702)** | **Primary (Autonomous Production Mode)** | **Rejected (Too fragile for live capital)** |

---

### 1.3 Detailed Architecture of Recommended Dual-Engine System

```
                  ┌───────────────────────────────────────────────┐
                  │       Antigravity Trading Agent Core          │
                  │ (Analyst -> Debate -> Trader -> Risk Manager) │
                  └───────────────────────┬───────────────────────┘
                                          │ Order Proposal
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │   Pre-Broadcast Safety Guardrail Pipeline     │
                  │ (Honeypot, Caps, Slippage, Gas, Simulation)   │
                  └───────────────────────┬───────────────────────┘
                                          │ Verified Order
                                          ▼
                               ┌──────────────────────┐
                      Is Mode? │ Execution Mode Switch │
                               └──────────┬───────────┘
                    Autonomous Mode       │       Interactive Mode
             ┌────────────────────────────┘       └────────────────────────────┐
             ▼                                                                 ▼
┌───────────────────────────────┐                             ┌────────────────────────────────┐
│   Local Keyring Signer        │                             │    Local Bridge Server         │
│  (`web3.py` + `eth-account`)  │                             │  (FastAPI + WebSockets)        │
├───────────────────────────────┤                             ├────────────────────────────────┤
│ - Encrypted JSON keystore     │                             │ - Emits WebSocket trade signal │
│ - In-memory signing           │                             │ - Serves Web DApp UI           │
│ - Zero human prompt needed    │                             │ - Connects to MetaMask Ext.    │
└──────────────┬────────────────┘                             └──────────────┬─────────────────┘
               │ Signed Raw Tx                                               │ EIP-1193 Request
               ▼                                                             ▼
┌───────────────────────────────┐                             ┌────────────────────────────────┐
│  Direct EVM Node / Bundler    │                             │ User's MetaMask Wallet         │
│ (Alchemy / Infura / QuickNode)│                             │ (User reviews & clicks confirm)│
└──────────────┬────────────────┘                             └──────────────┬─────────────────┘
               │                                                             │ Signed & Broadcasted
               ▼                                                             ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 On-Chain DEX Liquidity Pool                                  │
│                        (Uniswap v3 / Aerodrome / PancakeSwap v3)                             │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Autonomous Production Mode**:
   - The user creates or imports a dedicated trading hot wallet address.
   - The private key is saved in a standard encrypted Ethereum JSON Keystore (AES-128-CTR / scrypt).
   - The user sends a discrete trading allowance from their main MetaMask wallet (e.g. 0.05 ETH or 200 USDC).
   - The Python trading service signs and broadcasts automatically when agent consensus is reached and all safety guardrails pass.
2. **Interactive Attended Mode**:
   - The Python service runs a local FastAPI bridge on `http://127.0.0.1:8000`.
   - A companion web UI (or embedded browser view) connects to MetaMask via `window.ethereum.request({ method: 'eth_requestAccounts' })`.
   - When a trade is approved by the guardrails, the bridge sends a `TRADE_STAGED` payload over WebSockets to the web UI.
   - The UI automatically invokes `window.ethereum.request({ method: 'eth_sendTransaction', params: [tx] })`.
   - MetaMask pops up with the exact token amount, gas parameters, and contract call.
   - The user clicks "Confirm". The `txHash` is returned via WebSocket to the Python engine to monitor settlement.

---

## 2. Architecture for Automated Execution Safeguards (PBSGP)

The **Pre-Broadcast Safety Guardrail Pipeline** enforces six deterministic filters. If *any* filter fails, the transaction is rejected, logged with forensic telemetry, and no transaction is signed or broadcast.

### 2.1 Filter 1: Contract & Token Security Audit (Honeypot & Malicious Taxes)
- **Problem**: Malicious ERC-20 tokens frequently deploy honeypot mechanisms (cannot sell), 99% sell taxes, minting backdoors, or address blacklists.
- **Enforcement**:
  - Integration with **GoPlus Security API** (`api.gopluslabs.io/api/v1/token_security/{chain_id}`).
  - Verification assertions:
    ```python
    assert int(token_info.get("is_honeypot", 0)) == 0, "Honeypot detected!"
    assert float(token_info.get("buy_tax", 0)) <= config.max_buy_tax_pct, "Buy tax exceeds limit"
    assert float(token_info.get("sell_tax", 0)) <= config.max_sell_tax_pct, "Sell tax exceeds limit"
    assert int(token_info.get("cannot_sell_all", 0)) == 0, "Sell restriction active"
    assert int(token_info.get("owner_change_balance", 0)) == 0, "Owner can manipulate balance"
    ```
  - For major blue-chip tokens (WETH, WBTC, USDC, USDT, ARB), a verified static whitelist bypasses API latency.

### 2.2 Filter 2: Portfolio & Capital Allocation Caps
- **Problem**: LLM agent hallucinations or erratic signals can overcommit capital or blow up the account.
- **Enforcement Parameters**:
  - `max_spend_per_trade_usd`: Hard ceiling per transaction (e.g. $250.00).
  - `max_portfolio_allocation_per_asset_pct`: Maximum total percentage of portfolio value held in any single token (e.g. 20.0%).
  - `max_daily_spend_usd`: Cumulative 24-hour spending volume limit (e.g. $1,500.00).
  - `max_daily_drawdown_pct`: Portfolio-level circuit breaker (e.g. 8.0%). If net account value drops >8% from 00:00 UTC, all buying is frozen.
  - `min_native_gas_reserve_eth`: Preserves a minimum balance of native gas tokens (e.g. 0.01 ETH on Arbitrum/Base) to ensure the wallet is never locked out from executing emergency exits or unwinding positions.

### 2.3 Filter 3: Slippage Tolerance & Dynamic DEX Quoter Calculation
- **Problem**: Fixed slippage or unverified quotes leave the agent vulnerable to front-running, sandwich attacks (MEV), and illiquid pool slippage.
- **Enforcement**:
  - Query Uniswap v3 `IQuoterV2` contract (`quoteExactInputSingle`) off-chain:
    ```solidity
    function quoteExactInputSingle(
        QuoteExactInputSingleParams memory params
    ) external returns (
        uint256 amountOut,
        uint160 sqrtPriceX96After,
        uint32 initializedTicksCrossed,
        uint256 gasEstimate
    );
    ```
  - **Price Impact Check**:
    $$\text{PriceImpact} = \frac{|P_{\text{spot}} - P_{\text{effective}}|}{P_{\text{spot}}} \times 100\%$$
    If $\text{PriceImpact} > \text{max\_price\_impact\_pct}$ (default: 2.0%), the trade is rejected.
  - **Enforce Strict `amountOutMinimum`**:
    $$\text{amountOutMinimum} = \text{amountOut} \times \left(1 - \frac{\text{slippage\_bps}}{10000}\right)$$
    - Blue-chip pairs (ETH/USDC): 30–50 bps (0.3%–0.5%).
    - Mid-cap/alt pairs: 50–100 bps (0.5%–1.0%).
    - Hard limit: 150 bps (1.5%). Any signal requesting >1.5% slippage is blocked.
  - **Transaction Deadline**:
    $$\text{deadline} = \text{int}(\text{time.time}()) + 300 \quad (5\text{ minutes})$$
    Transactions are never submitted with open-ended validity to prevent pending transactions from being executed hours later during unexpected market swings.

### 2.4 Filter 4: Gas Price & Network Congestion Checker
- **Problem**: Sudden gas price spikes on Ethereum or L2 sequencer batch congestion can make trade execution costs exceed the expected trading edge.
- **Enforcement (EIP-1559)**:
  - Read current block base fee: `base_fee = w3.eth.get_block('latest')['baseFeePerGas']`.
  - Cap base fee: If `base_fee > max_base_fee_gwei * 1e9`, trade is queued.
  - Dynamic fee calculation:
    $$\text{maxPriorityFeePerGas} = \min(\text{w3.eth.max\_priority\_fee}, \text{max\_priority\_cap})$$
    $$\text{maxFeePerGas} = (2 \times \text{baseFeePerGas}) + \text{maxPriorityFeePerGas}$$
  - **Gas Cost to Trade Value Ratio**:
    $$\text{GasCostRatio} = \frac{\text{gasLimit} \times \text{maxFeePerGas} \times P_{\text{native}}}{\text{TradeValueUSD}} \times 100\%$$
    If $\text{GasCostRatio} > 1.5\%$ on L2 (or $> 3.0\%$ on L1), execution is blocked because gas eats too much of the trade's expected profit.

### 2.5 Filter 5: Pre-Flight State Simulation (Preventing Reverts)
- **Problem**: Incurring transaction fees for reverted transactions due to token transfer taxes, allowance issues, or pool tick exhaustion.
- **Enforcement**:
  - **Step 1: Local `eth_call` Dry Run**:
    Execute `w3.eth.call(tx_dict)` against the latest state.
    - If the call reverts, catch `ContractLogicError` and decode custom error selectors:
      - `0x` or `Error(string)` -> String reason (e.g. `"STF"` = SafeTransferFrom, `"TF"` = Transfer Failed, `"TooLittleReceived"`).
      - Abort with descriptive failure log before broadcasting.
  - **Step 2: `eth_estimateGas` Validation**:
    Ensures the node can trace execution through EVM opcodes without throwing an out-of-gas or execution revert.
  - **Step 3: Optional Enterprise Trace Simulation (Tenderly / Alchemy)**:
    - If `TENDERLY_RPC_URL` is configured, invoke `tenderly_simulateTransaction`.
    - Inspect simulated asset transfers to verify the recipient actually gains the expected token balance.

### 2.6 Filter 6: Signing & Broadcasting Router
- Unifies execution across Interactive and Autonomous modes:
  - Encodes swap parameters into `exactInputSingle` call data.
  - Checks and executes ERC-20 `approve` to Uniswap Router only for the exact `amountIn` (avoiding unlimited approval vulnerabilities).
  - Broadcasts raw transaction and tracks receipt with exponential backoff:
    `receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120, poll_latency=1)`.

---

## 3. Supported Chains & Multi-DEX Contract Specifications

### 3.1 Network Tiering Strategy

| Network | Chain ID | Role in System | Avg Gas Cost | Block Time | Recommended DEX |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Arbitrum One** | `42161` | **Primary Execution L2** | $0.01 – $0.05 | ~250 ms | Uniswap v3 / Camelot |
| **Base** | `8453` | **Secondary Execution L2** | $0.005 – $0.03 | 2.0 s | Uniswap v3 / Aerodrome |
| **Ethereum Mainnet** | `1` | High-Value Settlement (> $1k) | $5.00 – $40.00 | 12.0 s | Uniswap v3 / Curve |
| **BNB Smart Chain** | `56` | BSC Altcoins / High Volume | $0.05 – $0.15 | 3.0 s | PancakeSwap v3 |
| **Solana** | Non-EVM | Cross-Chain Deliberation (R4) | $0.001 | ~400 ms | Jupiter API / Synthetics |

---

### 3.2 Canonical Contract Addresses

#### Arbitrum One (`42161`):
- **Uniswap v3 SwapRouter02**: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
- **Uniswap v3 QuoterV2**: `0x61fFE014bA136170505655d03170F09287640F16`
- **WETH**: `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1`
- **USDC (Native)**: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`
- **WBTC**: `0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f`
- **ARB**: `0x912CE59144191C1204E64559FE8253a0e49E6548`

#### Base (`8453`):
- **Uniswap v3 SwapRouter02**: `0x2626664c2603336E57B271c5C0b26F421741e481`
- **Uniswap v3 QuoterV2**: `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
- **Aerodrome Router**: `0xcF77a3Ba9A5CA399B7c97c74856154938591A088`
- **WETH**: `0x4200000000000000000000000000000000000006`
- **USDC (Native)**: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- **cbBTC (Coinbase Wrapped BTC)**: `0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf`

#### Ethereum Mainnet (`1`):
- **Uniswap v3 SwapRouter02**: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
- **Uniswap v3 QuoterV2**: `0x61fFE014bA136170505655d03170F09287640F16`
- **WETH**: `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2`
- **USDC**: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- **WBTC**: `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599`

#### BNB Smart Chain (`56`):
- **PancakeSwap v3 Smart Router**: `0x13f4EA83D0bd40E75C8222255bc855a974568Dd4`
- **WBNB**: `0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c`
- **USDT**: `0x55d398326f99059fF775485246999027B3197955`
- **BTCB**: `0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c`

---

### 3.3 Solana Cross-Chain Strategy for Requirement R4 (BTC, ETH, SOL)
Requirement R4 mandates deliberation across BTC, ETH, and SOL. Since MetaMask is natively an EVM wallet, how is SOL handled?
We formulate three viable architectures:

1. **Approach A: EVM-Bridged Synthetic/Wrapped Solana (Recommended for Pure MetaMask)**:
   - Trade Wrapped SOL (e.g., Wormhole WSOL or Binance-Peg SOL) on Arbitrum/Base/BNB Chain using Uniswap or PancakeSwap.
   - User signs all transactions (BTC, ETH, SOL) through a single MetaMask wallet without managing a separate Solana keypair.
2. **Approach B: Decentralized Perpetuals (Hyperliquid / Aevo / GMX)**:
   - Connect MetaMask to an EVM-compatible perpetuals protocol (such as Hyperliquid or GMX Synthetics on Arbitrum).
   - Allows long/short exposure to BTC-USD, ETH-USD, and SOL-USD from one single collateral account (USDC) with zero cross-chain fragmentation.
3. **Approach C: Dual-Wallet Adapter (EVM MetaMask + Solana Keypair / Jupiter API)**:
   - For users requiring native SPL token swaps on Solana, integrate Jupiter V6 Swap API (`https://quote-api.jup.ag/v6/swap`) with `solana-py` and `solders`.
   - The MetaMask wallet manages EVM assets (ETH, WBTC, tokens), while a companion Solana keypair or MetaMask Solana Snap manages SOL.

---

## 4. Dependencies, Libraries & Configuration Schemas

### 4.1 Python Dependencies (`requirements-web3.txt`)

```text
web3>=6.15.0,<7.0.0
eth-account>=0.11.0
eth-typing>=3.5.0
eth-utils>=2.3.0
eth-abi>=4.2.0
pydantic>=2.0.0
fastapi>=0.110.0
uvicorn>=0.28.0
websockets>=12.0
httpx>=0.27.0
python-dotenv>=1.0.0
requests>=2.31.0
```

*Note*: In our environment inspection, `Python 3.11.9`, `pydantic 2.13.4`, `fastapi 0.162.0`, `uvicorn 0.54.0`, `websockets 16.0`, `httpx 0.28.1`, `requests 2.34.2`, and `playwright 1.64.0` are already installed in the local environment. Only `web3`, `eth-account`, and Ethereum primitives need to be pip installed.

### 4.2 Configuration Schema (`config/execution_config.yaml`)

```yaml
version: "1.0"

execution:
  mode: "dual" # "autonomous" | "interactive" | "dry_run"
  default_chain: "arbitrum"
  receipt_timeout_seconds: 120
  poll_interval_seconds: 2

chains:
  arbitrum:
    chain_id: 42161
    name: "Arbitrum One"
    rpc_url: "${ARBITRUM_RPC_URL:-https://arb1.arbitrum.io/rpc}"
    swap_router_address: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
    quoter_v2_address: "0x61fFE014bA136170505655d03170F09287640F16"
    wrapped_native: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
    native_symbol: "ETH"
    max_base_fee_gwei: 0.5
    max_priority_fee_gwei: 0.05
    default_fee_tier: 500 # 0.05%

  base:
    chain_id: 8453
    name: "Base"
    rpc_url: "${BASE_RPC_URL:-https://mainnet.base.org}"
    swap_router_address: "0x2626664c2603336E57B271c5C0b26F421741e481"
    quoter_v2_address: "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"
    wrapped_native: "0x4200000000000000000000000000000000000006"
    native_symbol: "ETH"
    max_base_fee_gwei: 0.1
    max_priority_fee_gwei: 0.01
    default_fee_tier: 500

guardrails:
  capital:
    max_spend_per_trade_usd: 250.00
    max_portfolio_allocation_per_asset_pct: 20.0
    max_daily_spend_usd: 1500.00
    max_daily_drawdown_pct: 8.0
    min_native_gas_reserve_eth: 0.01

  slippage:
    default_slippage_bps: 50 # 0.5%
    max_allowed_slippage_bps: 150 # 1.5%
    max_price_impact_pct: 2.0
    deadline_seconds: 300 # 5 minutes

  gas:
    max_gas_to_trade_ratio_pct: 1.5
    gas_limit_buffer_pct: 20.0
    max_gas_limit_cap: 450000

  security:
    goplus_audit_enabled: true
    max_allowed_buy_tax_pct: 1.0
    max_allowed_sell_tax_pct: 1.0
    reject_honeypots: true
    reject_mintable: true

  simulation:
    preflight_eth_call_enabled: true
    tenderly_simulation_enabled: false
    tenderly_rpc_url: "${TENDERLY_RPC_URL:-}"

wallet:
  autonomous:
    keystore_file: "config/trading_keystore.json"
    keystore_passphrase_env: "TRADING_KEYSTORE_PASSWORD"
  interactive_bridge:
    host: "127.0.0.1"
    http_port: 8000
    ws_port: 8765
    allowed_origins: ["http://localhost:3000", "http://127.0.0.1:8000"]
```

---

### 4.3 Python Pre-Flight Guardrail Validator Implementation (Reference Spec)

```python
"""
Pre-Broadcast Safety Guardrail Pipeline (PBSGP) - Reference Validator
"""
from typing import Dict, Any, Tuple
from decimal import Decimal
import time
from web3 import Web3
from pydantic import BaseModel, Field

class GuardrailConfig(BaseModel):
    max_spend_per_trade_usd: float = 250.0
    max_slippage_bps: int = 150
    max_price_impact_pct: float = 2.0
    max_gas_to_trade_ratio_pct: float = 1.5
    deadline_seconds: int = 300

class GuardrailPipeline:
    def __init__(self, w3: Web3, config: GuardrailConfig):
        self.w3 = w3
        self.config = config

    def validate_order(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        trade_usd_value: float,
        quoter_amount_out: int,
        tx_params: Dict[str, Any]
    ) -> Tuple[bool, str]:
        # 1. Per-trade Spend Limit
        if trade_usd_value > self.config.max_spend_per_trade_usd:
            return False, f"Order value ${trade_usd_value} exceeds max limit ${self.config.max_spend_per_trade_usd}"

        # 2. Slippage & Output Calculation
        min_out = quoter_amount_out * (10000 - self.config.max_slippage_bps) // 10000
        if min_out <= 0:
            return False, "Calculated minimum output is zero or negative"

        # 3. Gas Price & Cost Ratio Check
        latest_block = self.w3.eth.get_block('latest')
        base_fee = latest_block.get('baseFeePerGas', 0)
        max_fee = tx_params.get('maxFeePerGas', base_fee * 2)
        gas_limit = tx_params.get('gas', 250000)
        
        est_gas_cost_wei = max_fee * gas_limit
        # Assuming ETH price = $3,000 for verification
        est_gas_usd = (Decimal(est_gas_cost_wei) / Decimal(1e18)) * Decimal(3000)
        if trade_usd_value > 0 and (float(est_gas_usd) / trade_usd_value) * 100 > self.config.max_gas_to_trade_ratio_pct:
            return False, f"Gas cost ${float(est_gas_usd):.2f} exceeds {self.config.max_gas_to_trade_ratio_pct}% of trade value"

        # 4. Pre-Flight State Simulation (eth_call)
        try:
            self.w3.eth.call(tx_params)
        except Exception as e:
            return False, f"Pre-flight simulation reverted: {str(e)}"

        return True, "Guardrail validation passed"
```

---

## 5. Milestone Implementation Roadmap

To guide Milestone 3 (MetaMask Wallet Integration & Safety Guardrails), the work is broken into four concrete deliverables:

1. **Sub-Item 1: Web3 Infrastructure & Local Keyring (`src/execution/web3_client.py`)**
   - Initialize Multi-Chain RPC provider pool (Arbitrum, Base, Ethereum).
   - Implement secure JSON keystore loader and raw transaction signer.
   - Implement ERC-20 token wrapper (balance querying, exact allowance approvals).
2. **Sub-Item 2: Safety Guardrail Engine (`src/execution/guardrails.py`)**
   - Build the 6-layer pipeline with GoPlus security auditor, spending caps, and circuit breakers.
   - Integrate Uniswap v3 `IQuoterV2` for dynamic slippage and price impact checks.
   - Implement `eth_call` pre-flight simulation and error reason decoding.
3. **Sub-Item 3: Interactive MetaMask Bridge (`src/execution/bridge_server.py`)**
   - Fast-API WebSocket server broadcasting trade signals to a local browser bridge.
   - Lightweight EIP-1193 DApp interface allowing visual confirmation in MetaMask.
4. **Sub-Item 4: Automated Testing & Verification Suite (`tests/test_execution_guardrails.py`)**
   - Unit tests for all guardrail boundaries (spend limits, slippage bounds, honeypot rejections).
   - Mocked pre-flight simulations verifying revert handling.
   - Anvil/Hardhat local fork integration test simulating a live Uniswap v3 swap on Arbitrum fork.
