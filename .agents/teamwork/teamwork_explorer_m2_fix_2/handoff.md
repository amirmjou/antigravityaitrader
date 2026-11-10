# Handoff Report: Milestone 2 Test Suite Compatibility & Boundary Consistency

**Agent**: `teamwork_explorer_m2_fix_2`
**Date**: 2026-11-06T19:05:00Z
**Recipient**: `parent` (ID: `8738e4c1-d84c-4f83-b88d-7f67803aff6e`)
**Status**: Investigation Complete (Hard Handoff)

---

## 1. Observation

### Observation 1: Test Suite Status
Running the test suites via Python 3.11 yielded:
- `tests/adversarial/test_m2_guardrails_adversarial.py`: **24 passed, 8 failed** out of 32 tests.
- `tests/adversarial/test_m2_adversarial_challenge.py`: **26 passed, 0 failed** out of 26 tests.
- `tests/unit/test_execution.py`: **35 passed, 0 failed** out of 35 tests.
- `tests/e2e/test_tier1_f08_f14_wallet_guardrails.py`: **35 passed, 0 failed** out of 35 tests.
- `tests/e2e/run_all.py` (Tiers 1–4): **200 passed, 0 failed** out of 200 tests.
- `tests/adversarial/test_m1_*.py`: **52 passed, 0 failed** out of 52 tests.
Total across all test files: 337 passed, 8 failed (97.7% pass rate).

### Observation 2: Verbatim Failures in `test_m2_guardrails_adversarial.py`
The 8 failing tests in `tests/adversarial/test_m2_guardrails_adversarial.py` are:
1. `TestHostileInputs::test_zero_trade_value_behavior` (line 237):
   ```
   ZeroDivisionError: float division by zero
   execution\guardrails\pipeline.py:201: ZeroDivisionError
   tests\adversarial\test_m2_guardrails_adversarial.py:255: Failed: VULNERABILITY: PreBroadcastGuardrailPipeline raises unhandled ZeroDivisionError on trade_value_usd=0.0
   ```
2. `TestHostileInputs::test_negative_trade_value_behavior` (line 257):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:272: AssertionError: VULNERABILITY: Negative trade value was approved by guardrail pipeline!
   assert True is False
   ```
3. `TestHostileInputs::test_zero_amount_in_wei_behavior` (line 274):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:289: AssertionError: VULNERABILITY: Zero amount_in_wei was approved by guardrail pipeline!
   assert True is False
   ```
4. `TestHostileInputs::test_negative_amount_in_wei_behavior` (line 291):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:306: AssertionError: VULNERABILITY: Negative amount_in_wei was approved by guardrail pipeline!
   assert True is False
   ```
5. `TestHostileInputs::test_zero_portfolio_value_behavior` (line 308):
   ```
   ZeroDivisionError: float division by zero
   execution\guardrails\pipeline.py:139: ZeroDivisionError
   tests\adversarial\test_m2_guardrails_adversarial.py:326: Failed: VULNERABILITY: PreBroadcastGuardrailPipeline raises unhandled ZeroDivisionError on current_portfolio_value_usd=0.0
   ```
6. `TestHostileInputs::test_expired_or_negative_deadline_behavior` (line 328):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:344: AssertionError: VULNERABILITY: Negative/expired deadline was approved by guardrail pipeline!
   assert True is False
   ```
7. `TestHostileInputs::test_negative_slippage_behavior` (line 346):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:362: AssertionError: VULNERABILITY: Negative slippage was approved by guardrail pipeline!
   assert True is False
   ```
8. `TestHostileInputs::test_same_token_in_and_out_behavior` (line 364):
   ```
   tests\adversarial\test_m2_guardrails_adversarial.py:380: AssertionError: VULNERABILITY: Swapping a token for itself was approved by guardrail pipeline!
   assert True is False
   ```

### Observation 3: Exact Boundary Assertions in `tests/e2e/test_tier2_boundary_corner_cases.py`
1. Slippage: `test_bva_slippage_zero_bps_allowed` (lines 20–33):
   `SwapTransactionRequest(..., slippage_bps=0, ...)` -> `assert guardrail_pipeline.evaluate(req).approved is True`.
2. Deadline: `test_bva_deadline_1s_allowed` (lines 414–427):
   `SwapTransactionRequest(..., deadline_seconds=1, ...)` -> `assert guardrail_pipeline.evaluate(req).approved is True`.
3. Spend Cap: `test_bva_spend_cap_one_cent_allowed` (lines 169–183):
   `SwapTransactionRequest(..., trade_value_usd=0.01, ...)` -> allowed.
4. Drawdown: `test_bva_drawdown_zero_pct_allowed` (lines 243–255):
   `current_daily_drawdown_pct=0.0` -> `assert guardrail_pipeline.evaluate(req, current_daily_drawdown_pct=0.0).approved is True`.

### Observation 4: Test Fixture Conflict in `tests/adversarial/test_m2_adversarial_challenge.py`
In `tests/adversarial/test_m2_adversarial_challenge.py`:
- Lines 580–581 (`req_250`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 591–592 (`req_250_01`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 619–620 (`req_small`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 636–637 (`req_slip_100`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 649–650 (`req_slip_101`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 665–666 (`req_dl_301`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 687–688 (`req`): `token_in="0xSafe"`, `token_out="0xSafe"`
- Lines 719–720 (`req`): `token_in="0xSafe"`, `token_out="0xSafe"`
Tests at lines 587, 607, 626, 645, 679, 707 explicitly assert `approved is True` on these requests.

---

## 2. Logic Chain

1. **Step 1 (From Observation 2 to Input Bounds)**:
   In `execution/guardrails/pipeline.py`, the evaluate method only verifies upper bounds (`> 250`, `> 20%`, `> 100`, `> 300`, `> 120`). Zero and negative values bypass these checks. Furthermore, calculating concentration as `(new_asset_total / current_portfolio_value_usd) * 100.0` and gas ratio as `(gas_cost_usd / request.trade_value_usd) * 100.0` directly causes `ZeroDivisionError` when the divisor is 0.0. Therefore, explicit lower-bound guards are required for `trade_value_usd`, `current_portfolio_value_usd`, `amount_in_wei`, `deadline_seconds`, `slippage_bps`, and `token_in != token_out`.

2. **Step 2 (From Observation 3 to Exact Lower Bounds)**:
   - For `slippage_bps`: `test_bva_slippage_zero_bps_allowed` tests `slippage_bps=0` and requires `approved=True`. `test_negative_slippage_behavior` tests `slippage_bps=-50` and requires `approved=False`. Thus, the check MUST be `request.slippage_bps < 0`, not `<= 0`.
   - For `deadline_seconds`: `test_bva_deadline_1s_allowed` tests `deadline_seconds=1` and requires `approved=True`. `test_expired_or_negative_deadline_behavior` tests `deadline_seconds=-10` and requires `approved=False`. Thus, the check MUST be `request.deadline_seconds <= 0`.
   - For `trade_value_usd`: `test_bva_spend_cap_one_cent_allowed` tests `$0.01` and requires approval. `test_zero_trade_value_behavior` tests `$0.0` and requires rejection. Thus, the check MUST be `request.trade_value_usd <= 0.0`.
   - For `portfolio_value`: `current_portfolio_value_usd <= 0.0` must be rejected to prevent division by zero in Layer 2.

3. **Step 3 (From Observation 4 to Fixture Alignment)**:
   In `tests/adversarial/test_m2_guardrails_adversarial.py`, `test_same_token_in_and_out_behavior` expects self-swaps (`token_in == token_out`) to be rejected. When `token_in.lower() == token_out.lower()` rejection is added to `pipeline.py`, the 8 test requests in `test_m2_adversarial_challenge.py` that used dummy `token_in="0xSafe"` and `token_out="0xSafe"` will immediately be rejected, causing 4 test methods to fail. Updating `token_out` to `"0xSafeOut"` in `test_m2_adversarial_challenge.py` preserves the intended Layer 2/3/4/5 boundary assertions without self-swap conflicts.

4. **Step 4 (From Observation 1 & 2 to Model Architecture)**:
   Hostile tests instantiate `SwapTransactionRequest` with `0.0`, `-100.0`, `0`, `-10**16`, `-10`, and `-50`. If Pydantic model validation (`gt=0`, `ge=0`) is added to `SwapTransactionRequest`, these tests will raise `pydantic.ValidationError` before reaching `pipeline.evaluate()`, breaking the adversarial test harness. Therefore, all lower-bound checks must reside inside `pipeline.evaluate()`, not inside the Pydantic schema.

---

## 5. Caveats

1. **Dual Pipeline Definitions**: Both `execution/guardrails/pipeline.py` and `tests/e2e/harness.py` define `PreBroadcastGuardrailPipeline`. Both must receive the identical lower-bound checks to prevent behavioral divergence between unit/adversarial tests and E2E tests.
2. **Read-Only Scope**: In compliance with the explorer archetype, no production code or test files were modified during this investigation. All findings and code snippets are ready for implementation by the worker agent.

---

## 4. Conclusion

The 8 failing adversarial tests can be resolved with 100% cross-suite pass rates by:
1. Adding lower-bound checks to `execution/guardrails/pipeline.py` (and `tests/e2e/harness.py`):
   - Layer 1: Reject `request.token_in.lower() == request.token_out.lower()` and `request.amount_in_wei <= 0`.
   - Layer 2: Reject `request.trade_value_usd <= 0.0` and `current_portfolio_value_usd <= 0.0`.
   - Layer 3: Reject `request.slippage_bps < 0` (allow 0 bps) and `request.deadline_seconds <= 0` (allow >= 1s).
   - Layer 4: Add zero-division guard for `trade_value_usd <= 0.0`.
2. Aligning dummy fixture tokens in `tests/adversarial/test_m2_adversarial_challenge.py`:
   - Replace `token_out="0xSafe"` with `token_out="0xSafeOut"` at lines 581, 592, 620, 637, 650, 666, 688, 720.
3. Keeping `SwapTransactionRequest` in `tests/e2e/contracts.py` permissive (no Pydantic `gt=0` constraints).

---

## 5. Verification Method

Once the worker completes implementation:
```powershell
# 1. Verify all 32 adversarial guardrail tests pass (0 failures)
& "C:\Program Files\Python311\python.exe" -m pytest tests/adversarial/test_m2_guardrails_adversarial.py -v

# 2. Verify all 26 adversarial challenge tests pass (0 failures)
& "C:\Program Files\Python311\python.exe" -m pytest tests/adversarial/test_m2_adversarial_challenge.py -v

# 3. Verify all 35 unit execution tests pass (0 failures)
& "C:\Program Files\Python311\python.exe" -m pytest tests/unit/test_execution.py -v

# 4. Verify all 35 tier 1 wallet & guardrail tests pass (0 failures)
& "C:\Program Files\Python311\python.exe" -m pytest tests/e2e/test_tier1_f08_f14_wallet_guardrails.py -v

# 5. Verify all 200 platform E2E tests pass (0 failures)
& "C:\Program Files\Python311\python.exe" tests/e2e/run_all.py

# 6. Verify total suite pass rate (all 345 tests pass)
& "C:\Program Files\Python311\python.exe" -m pytest tests/ -v
```
**Invalidation Condition**: If any test fails, inspect whether `slippage_bps == 0` was rejected (should be allowed), `deadline_seconds == 1` was rejected (should be allowed), or `test_m2_adversarial_challenge.py` still has `token_out="0xSafe"` colliding with the self-swap guard.
