# Adversarial Challenge Report — Milestone 2: MetaMask Wallet Integration & 6-Layer Pre-Broadcast Safety Guardrails

**Challenger**: `teamwork_challenger_m2_2`  
**Target Milestone**: Milestone 2 (Features F08–F14)  
**Target Worker**: `teamwork_worker_m2_1`  
**Verdict**: **REJECT / REQUEST_CHANGES**  
**Date**: 2026-11-06  

---

## Challenge Summary

**Overall risk assessment**: **HIGH**

The implementation of Milestone 2 establishes genuine cryptographic foundations (`eth-account` keystore management with AES/scrypt encryption, EIP-191/EIP-712 signing, EIP-1559 gas estimation), an interactive FastAPI/WebSocket EIP-1193 bridge server, a dual-engine execution router, canonical multi-DEX routing for Arbitrum One and Base, and nominal 5-layer pre-broadcast guardrails.

All baseline tests pass:
- Unit tests (`tests/unit/test_execution.py`): 35/35 passed
- Tier 1 E2E tests (`tests/e2e/test_tier1_f08_f14_wallet_guardrails.py`): 35/35 passed
- Platform E2E tests (`tests/e2e/run_all.py`): 200/200 passed
- Adversarial challenge suite (`tests/adversarial/test_m2_adversarial_challenge.py`): 26/26 passed

However, rigorous empirical stress-testing against hostile, malformed, and boundary inputs revealed **failure modes and guardrail bypasses** in `execution/guardrails/pipeline.py` that must be hardened before this execution pipeline can be trusted with live on-chain capital:
1. **Unhandled `ZeroDivisionError` crashes**: If `trade_value_usd = 0.0` or `current_portfolio_value_usd = 0.0`, the pipeline crashes with an unhandled exception rather than returning a structured `GuardrailVerdict(approved=False)`.
2. **Missing lower-bound guardrail validation**: `trade_value_usd <= 0.0`, `amount_in_wei <= 0`, `deadline_seconds <= 0`, and `slippage_bps < 0` bypass safety checks and receive `approved=True`.
3. **No-op / Self-swap approval**: `token_in == token_out` is approved, causing guaranteed transaction failure or gas burn on-chain.

---

## Challenges

### [Critical] Challenge 1: Unhandled ZeroDivisionError Crashes Pipeline on Zero Input

- **Assumption challenged**: The worker assumed `trade_value_usd` and `current_portfolio_value_usd` are always non-zero positive numbers.
- **Attack scenario**:
  1. An upstream pricing feed returns 0 or a zero-value signal is emitted (`trade_value_usd = 0.0`).
  2. In `execution/guardrails/pipeline.py:201`:
     ```python
     gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0
     ```
     Python raises `ZeroDivisionError: float division by zero`.
  3. When an empty portfolio is evaluated (`current_portfolio_value_usd = 0.0`), line 139 executes:
     ```python
     concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0
     ```
     Python raises `ZeroDivisionError: float division by zero`.
- **Blast radius**: Service denial. Any zero-value signal abruptly crashes the safety evaluation thread rather than returning a structured rejection verdict to the caller.
- **Mitigation**:
  Enforce explicit positive input checks at the entry of `PreBroadcastGuardrailPipeline.evaluate()`:
  ```python
  if request.trade_value_usd <= 0.0:
      return GuardrailVerdict(
          approved=False,
          rejection_reason="Layer 2: trade_value_usd must be greater than zero.",
          layer_failed="Layer 2: Capital Allocation",
      )
  if current_portfolio_value_usd <= 0.0:
      return GuardrailVerdict(
          approved=False,
          rejection_reason="Layer 2: current_portfolio_value_usd must be greater than zero.",
          layer_failed="Layer 2: Capital Allocation",
      )
  ```

---

### [Critical] Challenge 2: Complete Guardrail Bypass on Negative Trade Value (`trade_value_usd < 0`)

- **Assumption challenged**: Upper-bound checking (`trade_value_usd > max_spend_per_trade_usd`) is sufficient for spend cap enforcement.
- **Attack scenario**:
  1. An agent proposal with a negative trade value (e.g. `-$100.0`) is passed to the pipeline.
  2. Layer 2 checks: `-100.0 > 250.0` is `False` (passes).
  3. Concentration checks: `(400.0 + (-100.0)) / 5000.0 = 6.0% <= 20.0%` (passes).
  4. Layer 4 calculates: `gas_ratio_pct = (gas_cost_usd / -100.0) * 100.0 < 0 <= 1.5%` (passes).
  5. The trade receives `approved=True` and proceeds to execution!
- **Blast radius**: Negative trade values bypass capital allocation checks entirely.
- **Mitigation**:
  Validate `request.trade_value_usd > 0.0` and `request.amount_in_wei > 0`.

---

### [High] Challenge 3: Negative or Expired Deadline (`deadline_seconds <= 0`) Approved

- **Assumption challenged**: Checking only `deadline_seconds > 300` prevents deadline violations.
- **Attack scenario**:
  1. Caller passes `deadline_seconds = -10` or `0`.
  2. Layer 3 evaluates `request.deadline_seconds > 300` -> `False` -> passes.
  3. `MultiDEXRouter.build_exact_input_single_params()` generates `deadline = int(time.time()) - 10`.
  4. Transaction broadcast to Uniswap v3 will revert immediately with `Transaction too old`, wasting user gas.
- **Blast radius**: On-chain revert and gas burn.
- **Mitigation**:
  Enforce `1 <= request.deadline_seconds <= 300` in Layer 3. If `request.deadline_seconds < 1`:
  ```python
  return GuardrailVerdict(
      approved=False,
      rejection_reason=f"Layer 3: Transaction deadline {request.deadline_seconds}s must be at least 1 second.",
      layer_failed="Layer 3: Dynamic Slippage",
  )
  ```

---

### [High] Challenge 4: Negative Slippage Tolerance and Zero/Negative Amounts Approved

- **Assumption challenged**: Slippage tolerance and token amounts are validated downstream.
- **Attack scenario**:
  1. Caller submits `slippage_bps = -50` or `amount_in_wei = 0`.
  2. Layer 3 checks `request.slippage_bps > self.config.max_slippage_bps` (`-50 > 100` is `False`) -> passes.
  3. A 0-token swap or inverted slippage parameter is approved for signing and broadcasting.
- **Blast radius**: Calldata corruption, non-standard swap execution, or wasted gas.
- **Mitigation**:
  Enforce `request.slippage_bps >= 0` and `request.amount_in_wei > 0`.

---

### [Medium] Challenge 5: Same Token In and Out Approved (`token_in == token_out`)

- **Assumption challenged**: Agents will never emit swaps with identical input and output tokens.
- **Attack scenario**:
  1. Proposal specifies `token_in = WETH` and `token_out = WETH`.
  2. All 5 guardrail layers pass because both tokens have clean GoPlus security records.
  3. Router submits a swap of WETH for WETH on Uniswap v3, which fails on-chain.
- **Blast radius**: Unnecessary transaction fees burned.
- **Mitigation**:
  Add an equality check in Layer 1 or pre-flight validation:
  ```python
  if request.token_in.lower() == request.token_out.lower():
      return GuardrailVerdict(
          approved=False,
          rejection_reason="Layer 1: token_in and token_out cannot be the same address.",
          layer_failed="Layer 1: Contract Security",
      )
  ```

---

## Stress Test Results

| # | Test Scenario | Expected Behavior | Actual Behavior | Result |
|---|---------------|-------------------|-----------------|--------|
| 1 | Keystore decryption with wrong password | Raise `ValueError` | `ValueError` raised | **PASS** |
| 2 | Keystore with tampered ciphertext | Raise decryption exception | Decryption error raised | **PASS** |
| 3 | Keystore with tampered MAC | Raise `ValueError` | `ValueError` raised | **PASS** |
| 4 | Corrupted keystore JSON structure | Raise parsing exception | Exception raised | **PASS** |
| 5 | Private key formatting (0x-prefix, 66 chars) | Length 66, valid hex | Verified 66 chars, 0x prefix | **PASS** |
| 6 | EIP-1193 bridge unsupported RPC method | Return code `-32601` | Returned code `-32601` | **PASS** |
| 7 | EIP-1193 bridge invalid `eth_sendTransaction` params | Return code `-32602` | Returned code `-32602` | **PASS** |
| 8 | EIP-1193 bridge chain switch to Base (8453) | Update `chain_id` to 8453 | Updated; `eth_chainId` is `0x2105` | **PASS** |
| 9 | EIP-1193 bridge transaction rejection flow | Status `rejected`, queue cleared | Removed from pending, status rejected | **PASS** |
| 10 | Sequential transaction nonce increments | Strict monotonic increment (+1) | 10 txs verified [0..9] | **PASS** |
| 11 | Nonce override & provider resync | Re-read pending count from node | Resynced to mock node count (55) | **PASS** |
| 12 | Nonce resync when node times out | Fail-fast (raise exception) | `ConnectionResetError` propagated | **PASS** |
| 13 | Multi-DEX router addresses (Arbitrum / Base) | Canonical SwapRouter02 & Aerodrome | Addresses match canonical deployments | **PASS** |
| 14 | Multi-DEX router unsupported chain ID (999999) | Raise `ValueError` | `ValueError: Unsupported chain_id` | **PASS** |
| 15 | Layer 1 GoPlus Honeypot detection (bool, str, int) | `approved=False` | Blocked across True, "1", 1 | **PASS** |
| 16 | Layer 1 GoPlus Buy/Sell tax boundary (1.00% vs 1.01%) | 1.00% pass, 1.01% fail | 1.00% approved, 1.01% blocked | **PASS** |
| 17 | Layer 1 GoPlus Token-in vs Token-out compromise | Either token bad -> blocked | Blocked on token_in or token_out | **PASS** |
| 18 | Layer 2 Spend Cap boundary ($250.00 vs $250.01) | $250.00 pass, $250.01 fail | $250.00 approved, $250.01 blocked | **PASS** |
| 19 | Layer 2 Concentration boundary (20.00% vs 20.01%) | 20.00% pass, 20.01% fail | 20.00% approved, 20.01% blocked | **PASS** |
| 20 | Layer 2 Drawdown circuit breaker (7.99% vs 8.00%) | 7.99% pass, 8.00% fail | 7.99% approved, 8.00% blocked | **PASS** |
| 21 | Layer 3 Slippage boundary (100 bps vs 101 bps) | 100 pass, 101 fail | 100 approved, 101 blocked | **PASS** |
| 22 | Layer 3 Price Impact boundary (2.00% vs 2.01%) | 2.00% pass, 2.01% fail | 2.00% approved, 2.01% blocked | **PASS** |
| 23 | Layer 3 Deadline boundary (300s vs 301s) | 300s pass, 301s fail | 300s approved, 301s blocked | **PASS** |
| 24 | Layer 4 Base Fee ceiling (120.0 vs 120.1 gwei) | 120.0 pass, 120.1 fail | 120.0 passed ceiling, 120.1 blocked | **PASS** |
| 25 | Layer 4 Gas-to-Trade ratio (1.46% vs 1.55%) | 1.46% pass, 1.55% fail | 1.46% approved, 1.55% blocked | **PASS** |
| 26 | Layer 5 Simulation custom revert decoding | Parse error into verdict | Correctly extracted revert message | **PASS** |
| 27 | Hostile: `trade_value_usd = 0.0` | `approved=False` | **CRASH**: `ZeroDivisionError` | **FAIL** |
| 28 | Hostile: `current_portfolio_value_usd = 0.0` | `approved=False` | **CRASH**: `ZeroDivisionError` | **FAIL** |
| 29 | Hostile: `trade_value_usd = -$100.00` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |
| 30 | Hostile: `amount_in_wei = 0` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |
| 31 | Hostile: `amount_in_wei = -10**16` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |
| 32 | Hostile: `deadline_seconds = -10` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |
| 33 | Hostile: `slippage_bps = -50` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |
| 34 | Hostile: `token_in == token_out` | `approved=False` | **BYPASS**: `approved=True` | **FAIL** |

---

## Unchallenged Areas

- **Live On-Chain RPC Nodes**: Tests were executed against deterministic high-fidelity mocks (`MockWeb3Provider`, `MockGoPlusClient`, `MockUniswapV3Quoter`). Live Ethereum/Arbitrum/Base RPC interaction with real network latency and gas price fluctuations was not tested due to offline development integrity mode.
- **Physical MetaMask Extension Browser DOM**: The EIP-1193 bridge was verified at the protocol level (FastAPI JSON-RPC 2.0 endpoints, WebSocket connection manager, REST staging endpoints). Physical browser extension popup rendering is deferred to Milestone 3 (Visualization UI).

---

## Recommendations for Worker

To achieve an **APPROVE** verdict in Iteration 2:
1. In `execution/guardrails/pipeline.py`:
   - Add input validation at the top of `evaluate()`:
     - Check `token_in.lower() != token_out.lower()`.
     - Check `request.trade_value_usd > 0.0`.
     - Check `request.amount_in_wei > 0`.
     - Check `request.deadline_seconds >= 1`.
     - Check `request.slippage_bps >= 0`.
     - Check `current_portfolio_value_usd > 0.0`.
2. Return clean `GuardrailVerdict(approved=False, rejection_reason=..., layer_failed=...)` whenever any of these checks fail.
3. Verify that all 32 tests in `tests/adversarial/test_m2_guardrails_adversarial.py` and 26 tests in `tests/adversarial/test_m2_adversarial_challenge.py` pass cleanly.
