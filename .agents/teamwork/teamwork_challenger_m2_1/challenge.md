# Adversarial Challenge Report — Milestone 2: Pre-Broadcast Guardrails & Wallet Integration

**Challenger**: `teamwork_challenger_m2_1`  
**Target Milestone**: Milestone 2 (Features F08–F14)  
**Target Worker**: `teamwork_worker_m2_1`  
**Verdict**: **REJECT / REQUEST_CHANGES**  
**Date**: 2026-11-06  

---

## Challenge Summary

**Overall risk assessment**: **CRITICAL**

While the worker successfully implemented the core structure for dual-engine wallet signing (`HotKeystoreSigner`, `EIP1193BridgeServer`), multi-DEX routing (`MultiDEXRouter`), and the nominal 5-layer guardrail pipeline (`PreBroadcastGuardrailPipeline`), empirical stress-testing revealed **8 critical vulnerabilities** where hostile or corrupted inputs either trigger an unhandled runtime crash (`ZeroDivisionError`) or completely bypass the guardrails and receive `approved=True` for live on-chain broadcast.

Because this pipeline serves as the ultimate pre-broadcast safety gate protecting real user funds in an autonomous trading environment, approving negative value trades or crashing on zero amount represents an unacceptable failure mode.

---

## Challenges

### [Critical] Challenge 1: Unhandled ZeroDivisionError on Zero Trade Value and Zero Portfolio Value

- **Assumption challenged**: The worker assumed `request.trade_value_usd` and `current_portfolio_value_usd` are always positive non-zero numbers.
- **Attack scenario**:
  1. An agent or corrupted signal emits a trade with `trade_value_usd = 0.0`.
  2. In `execution/guardrails/pipeline.py:201`:
     ```python
     gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0
     ```
     This triggers an unhandled `ZeroDivisionError: float division by zero`, crashing the evaluation thread instead of returning `GuardrailVerdict(approved=False, ...)`.
  3. Similarly, when `current_portfolio_value_usd = 0.0`, line 139 executes:
     ```python
     concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0
     ```
     Triggering another unhandled `ZeroDivisionError: float division by zero`.
- **Blast radius**: Pipeline service denial; evaluation loop terminates abruptly; caller receives an unhandled exception rather than a structured rejection verdict.
- **Mitigation**:
  Validate `request.trade_value_usd > 0.0` and `current_portfolio_value_usd > 0.0` at the entry of `evaluate()`. If `<= 0.0`, return:
  ```python
  GuardrailVerdict(
      approved=False,
      rejection_reason="Layer 2: trade_value_usd and portfolio_value_usd must be strictly positive.",
      layer_failed="Layer 2: Capital Allocation",
  )
  ```

---

### [Critical] Challenge 2: Complete Guardrail Bypass on Negative Trade Value (`trade_value_usd < 0`)

- **Assumption challenged**: The worker assumed capital allocation checks only need an upper bound check (`> max_spend_per_trade_usd`).
- **Attack scenario**:
  1. A hostile caller or calculation glitch passes `trade_value_usd = -100.0`.
  2. Layer 2 checks:
     - `request.trade_value_usd > 250.0` evaluates to `False` (`-100.0 > 250.0` is `False`).
     - `new_asset_total = 400.0 + (-100.0) = 300.0` -> `concentration_pct = 6.0% <= 20.0%` (`False`).
     - `drawdown >= 8.0%` (`False`).
  3. Layer 3 (quoter) passes.
  4. Layer 4 computes:
     `gas_ratio_pct = (gas_cost_usd / -100.0) * 100 = -0.06% <= 1.5%` (`False`).
  5. Layer 5 (simulation dry-run) executes and passes.
  6. Pipeline returns `GuardrailVerdict(approved=True)`!
- **Blast radius**: Negative trade values bypass the entire safety pipeline and are approved for on-chain execution.
- **Mitigation**:
  Reject any trade where `request.trade_value_usd <= 0.0` with `approved=False`.

---

### [High] Challenge 3: Zero and Negative `amount_in_wei` Approved for Broadcast

- **Assumption challenged**: The worker assumed token amounts are checked by quoter or simulation.
- **Attack scenario**:
  1. Caller submits `amount_in_wei = 0` (or `amount_in_wei < 0`) with nominal `trade_value_usd = 100.0`.
  2. Quoter calculates 0 output with 0% price impact.
  3. Gas ratio checks out against `trade_value_usd`.
  4. Simulation dry-run passes.
  5. Guardrail returns `approved=True` for a 0-token (or negative-token) swap.
- **Blast radius**: Burns user gas on a pointless 0-token transaction or broadcasts corrupted calldata.
- **Mitigation**:
  Enforce `request.amount_in_wei > 0` and `request.amount_out_min_wei >= 0`. If violated, return `GuardrailVerdict(approved=False, layer_failed="Layer 2: Capital Allocation")`.

---

### [Medium] Challenge 4: Negative or Expired Transaction Deadline Allowed

- **Assumption challenged**: Checking only `deadline_seconds > 300` is sufficient.
- **Attack scenario**:
  1. Caller submits `deadline_seconds = -10` or `0`.
  2. Guardrail checks `request.deadline_seconds > 300` -> `False` -> passes Layer 3.
  3. `MultiDEXRouter.build_exact_input_single_params()` constructs `deadline_timestamp = int(time.time()) - 10`.
  4. Broadcasted transaction will immediately revert on-chain (`Transaction too old`), wasting gas.
- **Blast radius**: Gas waste on expired transactions.
- **Mitigation**:
  Enforce `1 <= request.deadline_seconds <= 300`.

---

### [Medium] Challenge 5: Negative Slippage Tolerance Allowed

- **Assumption challenged**: Checking only `slippage_bps > max_slippage_bps` is sufficient.
- **Attack scenario**:
  1. Caller submits `slippage_bps = -50`.
  2. Guardrail checks `request.slippage_bps > 100` -> `False` -> passes Layer 3.
- **Blast radius**: Unintended negative bounds causing illogical order parameters.
- **Mitigation**:
  Enforce `0 <= request.slippage_bps <= self.config.max_slippage_bps`.

---

### [Medium] Challenge 6: Same-Token Swaps (`token_in == token_out`) Not Blocked

- **Assumption challenged**: Swapping an asset for itself would be caught by external contracts.
- **Attack scenario**:
  1. Caller submits `token_in == token_out == 0x82aF49447D8a07e3bd95BD0d56f35241523fBab1` (WETH to WETH).
  2. Passes Layer 1, Layer 2, Layer 3, Layer 4, and Layer 5.
  3. Returns `GuardrailVerdict(approved=True)`.
- **Blast radius**: User pays DEX swap fees and gas to swap an asset for itself.
- **Mitigation**:
  In Layer 1, verify `request.token_in.lower() != request.token_out.lower()`.

---

## Stress Test Results

Empirically verified in `tests/adversarial/test_m2_guardrails_adversarial.py` (32 tests total):

| # | Scenario | Expected Behavior | Actual Behavior | Result |
|---|----------|-------------------|-----------------|--------|
| 1 | Slippage 5000 bps | `approved=False`, Layer 3 | `approved=False`, Layer 3 | **PASS** |
| 2 | Price impact 100% | `approved=False`, Layer 3 | `approved=False`, Layer 3 | **PASS** |
| 3 | Token_in is Honeypot | `approved=False`, Layer 1 | `approved=False`, Layer 1 | **PASS** |
| 4 | Token_out is Honeypot | `approved=False`, Layer 1 | `approved=False`, Layer 1 | **PASS** |
| 5 | Token has 99% Sell Tax | `approved=False`, Layer 1 | `approved=False`, Layer 1 | **PASS** |
| 6 | Token has `cannot_sell_all` | `approved=False`, Layer 1 | `approved=False`, Layer 1 | **PASS** |
| 7 | Token is blacklisted | `approved=False`, Layer 1 | `approved=False`, Layer 1 | **PASS** |
| 8 | Zero trade value ($0.00) | `approved=False` | `ZeroDivisionError: float division by zero` | **FAIL** |
| 9 | Negative trade value (-$100.00) | `approved=False` | `approved=True` | **FAIL** |
| 10 | Zero `amount_in_wei` (0) | `approved=False` | `approved=True` | **FAIL** |
| 11 | Negative `amount_in_wei` (-10^16) | `approved=False` | `approved=True` | **FAIL** |
| 12 | Zero portfolio value ($0.00) | `approved=False` | `ZeroDivisionError: float division by zero` | **FAIL** |
| 13 | Expired deadline (-10s) | `approved=False` | `approved=True` | **FAIL** |
| 14 | Negative slippage (-50 bps) | `approved=False` | `approved=True` | **FAIL** |
| 15 | Same-token swap (WETH to WETH) | `approved=False` | `approved=True` | **FAIL** |
| 16 | Trade spend exact $250.00 | `approved=True` | `approved=True` | **PASS** |
| 17 | Trade spend $250.01 | `approved=False`, Layer 2 | `approved=False`, Layer 2 | **PASS** |
| 18 | Trade spend $100,000 | `approved=False`, Layer 2 | `approved=False`, Layer 2 | **PASS** |
| 19 | Concentration exact 20.0% | `approved=True` | `approved=True` | **PASS** |
| 20 | Concentration 20.02% | `approved=False`, Layer 2 | `approved=False`, Layer 2 | **PASS** |
| 21 | Drawdown exact 8.0% | `approved=False`, Layer 2 | `approved=False`, Layer 2 | **PASS** |
| 22 | Drawdown 7.9% | `approved=True` | `approved=True` | **PASS** |
| 23 | Gas base fee exact 120.0 gwei | Layer 4 evaluated | Layer 4 evaluated | **PASS** |
| 24 | Gas base fee 120.1 gwei | `approved=False`, Layer 4 | `approved=False`, Layer 4 | **PASS** |
| 25 | Gas ratio 4.54% (> 1.5%) | `approved=False`, Layer 4 | `approved=False`, Layer 4 | **PASS** |
| 26 | Revert TRANSFER_FAILED | `approved=False`, Layer 5 | `approved=False`, Layer 5 | **PASS** |
| 27 | Revert INSUFFICIENT_OUTPUT | `approved=False`, Layer 5 | `approved=False`, Layer 5 | **PASS** |
| 28 | Simulation burns 0 gas | On-chain tx history unchanged | On-chain tx history unchanged | **PASS** |
| 29 | Nonce increments monotonically | Nonces strictly 0, 1, 2... | Nonces strictly 0, 1, 2... | **PASS** |
| 30 | EIP-1559 math: max = 2*base + priority | Evaluates exact formula | Evaluates exact formula | **PASS** |
| 31 | Multi-DEX router addresses | Arb Uniswap + Base Aerodrome | Exact canonical addresses | **PASS** |
| 32 | Unknown chain_id | `ValueError` raised | `ValueError` raised | **PASS** |

**Summary**: 24 PASSED, 8 FAILED (75% pass rate under adversarial stress).

---

## Actionable Remediation Required from Worker

To achieve approval, the worker must update `execution/guardrails/pipeline.py` with rigorous input pre-validation:

1. **Token Distinctness Check (Layer 1)**:
   ```python
   if request.token_in.lower() == request.token_out.lower():
       return GuardrailVerdict(
           approved=False,
           rejection_reason="Layer 1: token_in and token_out cannot be the same address.",
           layer_failed="Layer 1: Contract Security",
       )
   ```

2. **Strict Positive Value Checks (Layer 2)**:
   ```python
   if request.trade_value_usd <= 0.0:
       return GuardrailVerdict(
           approved=False,
           rejection_reason=f"Layer 2: Per-trade spend ${request.trade_value_usd} must be strictly positive.",
           layer_failed="Layer 2: Capital Allocation",
       )

   if request.amount_in_wei <= 0:
       return GuardrailVerdict(
           approved=False,
           rejection_reason="Layer 2: amount_in_wei must be strictly positive.",
           layer_failed="Layer 2: Capital Allocation",
       )

   if current_portfolio_value_usd <= 0.0:
       return GuardrailVerdict(
           approved=False,
           rejection_reason="Layer 2: Current portfolio value must be strictly positive.",
           layer_failed="Layer 2: Capital Allocation",
       )
   ```

3. **Slippage and Deadline Range Checks (Layer 3)**:
   ```python
   if request.slippage_bps < 0 or request.slippage_bps > self.config.max_slippage_bps:
       return GuardrailVerdict(
           approved=False,
           rejection_reason=f"Layer 3 Requested slippage {request.slippage_bps} bps outside allowed range (0 to {self.config.max_slippage_bps} bps).",
           layer_failed="Layer 3: Dynamic Slippage",
       )

   if request.deadline_seconds <= 0 or request.deadline_seconds > 300:
       return GuardrailVerdict(
           approved=False,
           rejection_reason=f"Layer 3 Transaction deadline {request.deadline_seconds}s outside allowed range (1s to 300s).",
           layer_failed="Layer 3: Dynamic Slippage",
       )
   ```

---

## Unchallenged Areas

- Live mainnet RPC broadcast: Out of scope per offline test harness design.
- Physical MetaMask browser popup rendering: Handled via FastAPI JSON-RPC and WebSocket bridge protocol.
