## 2026-11-06T18:26:26Z
You are teamwork_worker_m2_1, assigned to implement Milestone 2: MetaMask Wallet Integration & 6-Layer Pre-Broadcast Safety Guardrails (Features F08–F14).

Your working directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m2_1\
Parent Orchestrator Conversation ID: 8738e4c1-d84c-4f83-b88d-7f67803aff6e

MANDATORY FILES TO READ FIRST:
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read verbatim before starting work)
- c:\Users\AmirM\Documents\Agentic trading\PROJECT.md (§ Features F08–F14 and § Interface Contracts 1 & 2)
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_survey_2\handoff.md and survey_report.md
- c:\Users\AmirM\Documents\Agentic trading\tests\e2e\contracts.py, tests\e2e\harness.py, and tests\e2e\test_tier1_f08_f14_wallet_guardrails.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

EXCLUSIVE WRITE BOUNDARIES:
You own exclusively:
- `execution/`
- `tests/unit/test_execution.py`
- `.agents/teamwork/teamwork_worker_m2_1/`
DO NOT modify files outside your assigned write boundaries (do not modify `core/`, `tests/e2e/`, `tests/adversarial/`, etc.).

DELIVERABLES & IMPLEMENTATION REQUIREMENTS:
1. `execution/wallet/`:
   - `hot_signer.py`: Autonomous hot keystore signer using `eth-account` (encrypted keystore handling, private key management, nonce tracking, EIP-1559 gas fee estimation, and transaction signing).
   - `eip1193_bridge.py`: Interactive EIP-1193 FastAPI bridge server exposing JSON-RPC endpoints (`/rpc`, `/request-accounts`, `/send-transaction`, `/sign-typed-data`) and WebSocket status updates for MetaMask browser extension connection.
   - `router.py`: `DualEngineWalletRouter` supporting both `hot_keystore` and `eip1193_metamask` modes, dispatching to target RPC/web3 providers, tracking block confirmations, and handling transaction reverts.
2. `execution/guardrails/`:
   - `pipeline.py`: `PreBroadcastGuardrailPipeline` coordinating the 5 safety layers:
     - Layer 1 (Contract Security): GoPlus API honeypot check, buy/sell tax <= 1% ceiling, blacklist check.
     - Layer 2 (Capital Allocation): Max $250 spend per trade cap, max 20% single-asset portfolio concentration, 8% rolling 24h drawdown circuit breaker.
     - Layer 3 (Dynamic Slippage): Uniswap v3 `IQuoterV2` pricing (Arbitrum One and Base), 30–100 bps slippage limit, <=2% price impact threshold, 300-second execution deadline.
     - Layer 4 (Gas & Congestion): EIP-1559 base fee check against gas ceiling, max priority fee, and gas cost to trade value ratio ceiling <= 1.5%.
     - Layer 5 (Pre-Flight Simulation): `eth_call` dry-run simulation against live block state with custom revert reason decoding.
   - Return structured `GuardrailVerdict` with approval status, rejection reason, and failed layer.
3. `execution/routers/`:
   - `dex_router.py`: Multi-DEX execution router for Arbitrum One (`chain_id=42161`) and Base (`chain_id=8453`) using Uniswap v3 `SwapRouter02` and Aerodrome.
4. `execution/__init__.py`: Clean public API exports matching `PROJECT.md` contracts.
5. Unit & Regression Testing:
   - Create comprehensive unit tests in `tests/unit/test_execution.py`.
   - Run `python -m pytest "tests/e2e/test_tier1_f08_f14_wallet_guardrails.py" -v` and ensure all 35 tests PASS.
   - Run platform-wide E2E tests: `python tests/e2e/run_all.py` (200/200 tests must pass).
   - Run core tests: `python -m pytest "core/tests/" -q` (1420 tests must continue passing).

OUTPUT REQUIREMENTS:
- Record all changes in `changes.md` in your working directory.
- Deliver `handoff.md` (Hard Handoff) with:
  1. Observation (exact commands run and test outputs)
  2. Logic Chain (rationale and architecture)
  3. Caveats (dependencies, mock boundaries)
  4. Conclusion
  5. Verification Method (reproducible commands)
- Notify the parent orchestrator via `send_message` with your completion report.
