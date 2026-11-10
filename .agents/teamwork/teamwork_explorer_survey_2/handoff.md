# Handoff Report — Survey of MetaMask Wallet Connectivity & Safety Guardrails (R2)

**Milestone**: Phase 0 — Survey & Architecture Discovery  
**Agent**: `teamwork_explorer_survey_2`  
**Handoff Type**: Hard Handoff (Investigation Complete)  
**Date**: 2026-11-06  

---

## 1. Observation

1. **Environment State**:
   - Python version: `Python 3.11.9` (`python --version`).
   - Node runtime: `v24.21.0` (`node --version`), running via Electron shim `C:\Users\AmirM\AppData\Local\Programs\antigravity\Antigravity.exe` with `ELECTRON_RUN_AS_NODE=1`.
   - Python packages installed: `fastapi 0.162.0`, `uvicorn 0.54.0`, `websockets 16.0`, `pydantic 2.13.4`, `playwright 1.64.0`, `httpx 0.28.1`, `requests 2.34.2`, `cryptography 49.0.0`.
   - Missing EVM packages: `web3`, `eth-account`, `eth-typing`, `eth-utils`, `eth-abi` are not yet installed in the current Python environment (`python -m pip list`).
2. **Project Scope Document**:
   - `ORIGINAL_REQUEST.md:19-21`: Requirement R2 states: *"Connect the system to the user's MetaMask wallet to enable live on-chain automated transaction signing, incorporating configurable execution safeguards (maximum allocation caps, slippage limits, and transaction verification)."*
   - `ORIGINAL_REQUEST.md:34-37`: Acceptance criteria state: *"MetaMask integration signs and broadcasts transactions on-chain. Safeguards against unintended execution (per-trade spend limit, slippage tolerance, gas thresholds) are enforced prior to transaction broadcast."*
3. **MetaMask Protocol Architecture**:
   - MetaMask operates as an EIP-1193 non-custodial signer. Private keys are encrypted inside the user's browser extension or mobile hardware enclave and cannot be accessed headlessly via standard RPCs without user confirmation.
   - `@metamask/connect-evm` and `@walletconnect/sign-client` facilitate remote terminal/CLI connections, but every transaction dispatch triggers an interactive prompt or QR code push notification.
   - ERC-7715 (`wallet_requestExecutionPermissions`) enables session keys with scoped spending limits and expiry, supported via MetaMask Smart Accounts Kit.
   - Local `eth-account` with encrypted JSON keystores (AES-128-CTR) allows 100% headless, sub-second transaction signing in Python.
4. **DEX Contract Architecture**:
   - Uniswap v3 SwapRouter02 is deployed at `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45` on Arbitrum One (`42161`) and Ethereum Mainnet (`1`), and at `0x2626664c2603336E57B271c5C0b26F421741e481` on Base (`8453`).
   - Off-chain swap output quotes, tick crossings, and price impacts can be computed via `IQuoterV2` (`0x61fFE014bA136170505655d03170F09287640F16` on Arbitrum).
   - Pre-flight transaction simulation can be executed locally via `w3.eth.call(tx_params)` to detect reverts without gas expenditure, and optionally augmented via Tenderly (`tenderly_simulateTransaction`) or Alchemy (`alchemy_simulateExecution`).

---

## 2. Logic Chain

1. **Step 1 (Requirement vs MetaMask Reality)**:
   - Observation 2 mandates *automated on-chain transaction signing* via MetaMask, while Observation 3 establishes that MetaMask extension by design blocks automated background signing without user confirmation modal interaction.
   - Therefore, a monolithic architecture relying solely on the MetaMask browser extension cannot operate headlessly 24/7 unless a human clicks every prompt or a fragile DOM scraper is used (which is rejected for production capital safety).
2. **Step 2 (Deduction of the Dual-Engine Architecture)**:
   - To satisfy both automated 24/7 execution and live MetaMask connection, the system must separate execution into two complementary modes:
     - **Interactive Attended Mode**: Uses a local FastAPI + WebSocket bridge serving an EIP-1193 web UI that communicates directly with the user's MetaMask extension for staged visual reviews.
     - **Autonomous Sub-Account Mode**: Uses a local `eth-account` signer initialized from an encrypted keystore, funded with capped trading capital directly from the user's primary MetaMask wallet.
3. **Step 3 (Safety Guardrail Pipeline Design)**:
   - Observation 2 mandates safeguards (spend limits, slippage, gas thresholds) prior to broadcasting.
   - From Observations 3 & 4, DEX swaps are vulnerable to front-running, high slippage, gas spikes, and malicious contract honeypots.
   - Therefore, an order must pass through a strict serial pipeline before signing:
     - Layer 1 (Security): GoPlus API checks `is_honeypot == 0` and buy/sell tax $\le 1\%$.
     - Layer 2 (Capital): Enforces per-trade spend ceiling, 20% single-asset cap, and 8% daily portfolio drawdown breaker.
     - Layer 3 (Slippage): Queries `IQuoterV2`, caps price impact at 2.0%, calculates `amountOutMinimum` with 30–100 bps slippage, and sets a 300-second deadline.
     - Layer 4 (Gas): Verifies EIP-1559 base fee is below cap and total gas cost does not exceed 1.5% of trade value.
     - Layer 5 (Simulation): Executes `eth_call` dry-run against live state to catch contract reverts before broadcasting.
4. **Step 4 (Network Selection for Execution)**:
   - On Ethereum L1, a Uniswap swap costs ~150k–250k gas ($5 to $40+), which violates the gas-to-trade ratio for small/medium trades.
   - On Arbitrum One and Base (L2), gas costs are $0.005–$0.05 with ~250ms–2s finality.
   - Therefore, Arbitrum One and Base must serve as the primary execution targets, while Solana deliberation (R4) is bridged via Wrapped SOL, Perps (Hyperliquid/GMX), or a dedicated Solana adapter.

---

## 3. Caveats

1. **ERC-7715 Production Adoption**: While MetaMask Smart Accounts Kit supports ERC-7715 Advanced Permissions, standard EOA accounts on Ethereum Mainnet do not yet have native session key support until EIP-7702 is finalized in the Pectra hard fork. Thus, the Dual-Engine model (Keystore Hot Wallet + MetaMask Bridge) is recommended for immediate implementation.
2. **RPC Rate Limits**: Public RPC endpoints (`arb1.arbitrum.io/rpc`, `mainnet.base.org`) enforce rate limits. High-frequency quoting or simulation requires an API key from Alchemy, Infura, or QuickNode.
3. **Simulated State Drift**: An `eth_call` simulation confirms transaction validity at block $N$; if market state changes dramatically between simulation and block $N+1$, the transaction relies on the enforced `amountOutMinimum` and deadline parameters to safely revert on-chain rather than execute with excessive slippage.

---

## 4. Conclusion

1. **Architecture Finalized**: The live execution subsystem will implement a **Dual-Engine Execution Architecture** consisting of a **Local Hot-Signer Keyring (`eth-account`)** for autonomous 24/7 trading and a **FastAPI/WebSocket MetaMask Bridge** for interactive attended confirmation.
2. **Guardrail Pipeline Defined**: All orders must pass a 6-layer Pre-Broadcast Safety Guardrail Pipeline (GoPlus honeypot check, capital caps, dynamic `IQuoterV2` slippage & price impact, EIP-1559 gas ratio, `eth_call` simulation, and signing router).
3. **Target Chains Mapped**: Arbitrum One (Chain ID 42161) and Base (Chain ID 8453) are the primary execution targets for Uniswap v3 and Aerodrome. Solana exposure is unified via EVM Wrapped Solana or Decentralized Perpetuals.
4. **Dependencies Cataloged**: Installation of `web3>=6.15.0` and `eth-account>=0.11.0` will complete the Python execution stack.

---

## 5. Verification Method

To independently verify the findings and technical artifacts of this survey:

1. **Inspect Survey Report**:
   - Read `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_survey_2\survey_report.md`.
   - Verify that all comparison matrices, contract addresses (Uniswap v3 SwapRouter02 on Arbitrum `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`, Base `0x2626664c2603336E57B271c5C0b26F421741e481`), configuration YAML schemas, and reference Python validation code are present and complete.
2. **Verify Environment Readiness**:
   - Run `python -c "import fastapi, uvicorn, pydantic, websockets, httpx; print('Core web/network stack ready!')"` to verify prerequisites.
3. **Test RPC & Quoter Connectivity (Once `web3` is installed)**:
   - Connect `web3.py` to `https://arb1.arbitrum.io/rpc`.
   - Call `eth_blockNumber` and query Uniswap v3 Quoter contract to confirm off-chain quote generation.
4. **Invalidation Conditions**:
   - If MetaMask releases an unattended background signing daemon for browser extensions without user interaction, the Dual-Engine model can be simplified to a single extension bridge.
   - If L2 gas costs exceed 10% of trade value during extreme congestion, the gas ratio filter will trip and pause execution as designed.
