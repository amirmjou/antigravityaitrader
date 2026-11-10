# Changes Log — Milestone 2: MetaMask Wallet Integration & 6-Layer Pre-Broadcast Safety Guardrails

**Agent**: `teamwork_worker_m2_1`  
**Milestone**: Milestone 2 (Features F08–F14)  
**Date**: 2026-11-06  

---

## 1. Summary of Changes

Implemented the complete live EVM execution and safety guardrail subsystem for the Antigravity Agentic Trading Platform within the assigned write boundaries:
- `execution/`
- `tests/unit/test_execution.py`
- `.agents/teamwork/teamwork_worker_m2_1/`

All implementations are genuine, maintain real state, utilize standard cryptography (`eth-account` AES/scrypt keystore encryption, EIP-191 personal signing, EIP-712 structured typed data signing, EIP-1559 gas fee estimation), FastAPI & WebSocket interactive bridge server, serial 5-layer safety pipeline, and multi-chain DEX routing across Arbitrum One and Base.

---

## 2. Detailed File Modifications

### A. `execution/wallet/`
1. `execution/wallet/hot_signer.py`:
   - `HotKeystoreSigner`: Autonomous keystore signer based on `eth-account`.
   - Supports creating new accounts (`create_new`), importing from raw private keys (`from_private_key`), decrypting/importing from encrypted JSON keystores (`from_keystore_json`, `from_keystore_file`), and exporting encrypted keystores (`export_keystore`, `save_keystore_file`).
   - Nonce management: internal nonce tracking (`get_nonce`, `set_nonce`, `resync_nonce`) auto-incrementing per transaction.
   - EIP-1559 gas estimation: computes `maxPriorityFeePerGas` and `maxFeePerGas = (2 * baseFeePerGas) + maxPriorityFeePerGas`.
   - Transaction signing: signs EIP-1559 type 2 transactions with auto-populated parameters.
   - Message signing: EIP-191 personal message signing (`sign_message`).
   - Typed data signing: EIP-712 structured typed data signing (`sign_typed_data`).

2. `execution/wallet/eip1193_bridge.py`:
   - `EIP1193BridgeServer`: FastAPI server providing JSON-RPC and WebSocket bridge.
   - JSON-RPC 2.0 endpoint (`/rpc`) handling `eth_accounts`, `eth_requestAccounts`, `eth_chainId`, `net_version`, `eth_sendTransaction`, `eth_signTypedData_v4`, `personal_sign`, `wallet_switchEthereumChain`.
   - REST staging endpoints: `/request-accounts`, `/send-transaction`, `/sign-typed-data`, `/confirm-transaction`, `/status`, `/pending`.
   - WebSocket broadcast manager at `/ws` and `/ws/status` emitting real-time events (`CONNECTED`, `TRADE_STAGED`, `TX_CONFIRMED`, `TX_REJECTED`) and receiving user confirmations.
   - `create_bridge_app()` factory function.

3. `execution/wallet/router.py`:
   - `DualEngineWalletRouter`: Dispatches between `hot_keystore` and `eip1193_metamask` modes.
   - Integrates with both mock and real Web3 RPC providers.
   - Tracks block numbers, mined transactions, gas units consumed, and effective gas price.
   - Gracefully handles EVM reverts, capturing revert reasons.

4. `execution/wallet/__init__.py`:
   - Public API exports for wallet integration.

---

### B. `execution/guardrails/`
1. `execution/guardrails/pipeline.py`:
   - `PreBroadcastGuardrailPipeline`: Coordinates the serial 5-layer pre-broadcast safety pipeline.
   - **Layer 1 (Contract Security)**: Queries GoPlus Token Security API for both `token_in` and `token_out`, checking for honeypots (`is_honeypot == 1`), buy/sell tax ceilings (<=1.0%), and transfer restrictions (`cannot_sell_all`, `is_blacklisted`).
   - **Layer 2 (Capital Allocation)**: Enforces hard per-trade spend limit ($250.00 max), single-asset portfolio concentration ceiling (<=20.0%), and rolling 24-hour drawdown circuit breaker (<=8.0%).
   - **Layer 3 (Dynamic Slippage)**: Uniswap v3 `IQuoterV2` pricing, slippage tolerance verification (30–100 bps), price impact ceiling (<=2.0%), and strict transaction deadline (<=300 seconds).
   - **Layer 4 (Gas & Congestion)**: EIP-1559 base fee check against network gas ceiling, priority fee cap, and gas-cost-to-trade-value ratio check (<=1.5%).
   - **Layer 5 (Pre-Flight Simulation)**: Executes `eth_call` dry run against live block state to catch contract reverts and decode error reasons before broadcasting without burning gas.
   - Returns structured `GuardrailVerdict` with full execution telemetry.

2. `execution/guardrails/__init__.py`:
   - Public exports for guardrails module.

---

### C. `execution/routers/`
1. `execution/routers/dex_router.py`:
   - `MultiDEXRouter`: DEX router for Arbitrum One (`chain_id=42161`) and Base (`chain_id=8453`) using Uniswap v3 `SwapRouter02` and Aerodrome.
   - Canonical contract addresses:
     - Arbitrum One: Uniswap v3 SwapRouter02 `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`, QuoterV2 `0x61fFE014bA136170505655d03170F09287640F16`.
     - Base: Uniswap v3 SwapRouter02 `0x2626664c2603336E57B271c5C0b26F421741e481`, QuoterV2 `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`, Aerodrome Router `0xcF77a3Ba9A5CA399B7c97c74856154938591A088`.
   - Transaction construction: builds `ExactInputSingleParams` struct parameters and ERC-20 approval transactions.
   - Dispatch delegation via `route_and_execute()`.

2. `execution/routers/__init__.py`:
   - Public exports for routers module.

---

### D. `execution/__init__.py`
Exports public symbols matching `PROJECT.md`:
- `HotKeystoreSigner`
- `EIP1193BridgeServer`, `create_bridge_app`
- `DualEngineWalletRouter`
- `PreBroadcastGuardrailPipeline`
- `MultiDEXRouter`, `DEXRouterConfig`, `KNOWN_DEX_CONFIGS`
- `GuardrailVerdict`, `ChainExecutionConfig`, `SwapExecutionResult`, `SwapTransactionRequest`

---

### E. `tests/unit/test_execution.py`
Created comprehensive unit test suite containing 35 tests:
- `TestHotKeystoreSigner`: 9 tests (account creation, key import, keystore encryption/decryption, persistence, nonce tracking, EIP-1559 fee estimation, transaction signing, personal message signing, typed data signing).
- `TestEIP1193BridgeServer`: 5 tests (status endpoint, accounts request, transaction staging & confirmation, transaction rejection, JSON-RPC methods).
- `TestDualEngineWalletRouter`: 3 tests (hot keystore execution, MetaMask bridge execution, revert handling).
- `TestPreBroadcastGuardrailPipeline`: 8 tests (honeypot detection, high tax rejection, per-trade cap, concentration cap, drawdown circuit breaker, dynamic slippage & price impact, gas congestion, simulation revert).
- `TestMultiDEXRouter`: 5 tests (router address resolution, swap transaction building, approval transaction building, unsupported chain error, execution delegation).
- `TestExecutionEdgeCases`: 5 tests (keystore wrong password, unsupported signer mode, transfer restrictions, nonce resync, bridge app factory).
