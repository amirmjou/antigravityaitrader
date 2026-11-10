# Comprehensive Vulnerability Analysis & Hardening Design
## Milestone 2 Remediation: Input Sanitization & Division-by-Zero Hardening (Features F08–F14)

- **Agent**: `teamwork_explorer_m2_fix_1` (Read-Only Explorer)
- **Target Component**: `execution/guardrails/pipeline.py` (`PreBroadcastGuardrailPipeline`)
- **Parent Orchestrator**: `8738e4c1-d84c-4f83-b88d-7f67803aff6e`
- **Date**: 2026-11-06

---

## 1. Executive Summary

Milestone 2 establishes genuine cryptographic foundations (`eth-account` keystore management with AES/scrypt encryption, EIP-191/EIP-712 signing, EIP-1559 gas estimation), an interactive FastAPI/WebSocket EIP-1193 bridge server, a dual-engine execution router, canonical multi-DEX routing for Arbitrum One and Base, and nominal 5-layer pre-broadcast guardrails.

All baseline test suites pass:
- **Unit tests** (`tests/unit/test_execution.py`): 35/35 passed
- **Tier 1 E2E tests** (`tests/e2e/test_tier1_f08_f14_wallet_guardrails.py`): 35/35 passed
- **Platform E2E runner** (`tests/e2e/run_all.py`): 200/200 passed across Tiers 1-4

However, empirical hostile input stress testing in `tests/adversarial/test_m2_guardrails_adversarial.py` revealed **8 distinct failure modes** (24 passed, 8 failed) in `PreBroadcastGuardrailPipeline.evaluate()`:
1. **ZeroDivisionError on Zero Trade Value**: `trade_value_usd = 0.0` crashes at line 201 (`gas_cost_usd / request.trade_value_usd`).
2. **Negative Trade Value Bypass**: `trade_value_usd = -100.0` satisfies `< $250.00` and yields negative gas ratio `< 1.5%`, returning `approved=True`.
3. **Zero Token Amount In Bypass**: `amount_in_wei = 0` passes all layers and returns `approved=True`.
4. **Negative Token Amount In Bypass**: `amount_in_wei = -10**16` passes all layers and returns `approved=True`.
5. **ZeroDivisionError on Zero Portfolio Value**: `current_portfolio_value_usd = 0.0` crashes at line 139 (`new_asset_total / current_portfolio_value_usd`).
6. **Negative/Expired Deadline Bypass**: `deadline_seconds = -10` satisfies `<= 300` and returns `approved=True`.
7. **Negative Slippage Bypass**: `slippage_bps = -50` satisfies `<= max_slippage_bps` and returns `approved=True`.
8. **Self-Swap Bypass**: `token_in == token_out` passes GoPlus checks and returns `approved=True`.

In addition, an investigation into peer test suites revealed a **critical test fixture defect** in `tests/adversarial/test_m2_adversarial_challenge.py`: lines 580, 592, 620, 637, 650, 666, 688, 720 used `token_in="0xSafe", token_out="0xSafe"`. Once self-swap rejection is implemented in `pipeline.py`, those test cases would falsely fail at Layer 1 unless updated to distinct safe addresses (`0xSafeIn`, `0xSafeOut`).

---

## 2. Evidence Chain & Root Cause Analysis

### Vulnerability 1: ZeroDivisionError on Zero Trade Value (`trade_value_usd = 0.0`)
- **Direct Observation**:
  Executing `pipeline.evaluate(req)` with `trade_value_usd = 0.0` raises:
  `ZeroDivisionError: float division by zero` in `execution/guardrails/pipeline.py:201`:
  `gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0`
- **Root Cause**:
  `trade_value_usd` is checked in Layer 2 for upper bound (`request.trade_value_usd > self.max_spend_per_trade_usd`), but has no lower bound check (`<= 0.0`). As a result, `0.0` passes Layer 2 and Layer 3, reaching Layer 4 where it acts as the divisor for the gas-to-trade cost ratio calculation.
- **Architectural Placement**:
  `Layer 2: Capital Allocation`. An order with zero monetary value violates the capital allocation contract and must be rejected before reaching quoter (Layer 3) or gas computation (Layer 4). Defensively, Layer 4 must also guard against division by zero.

### Vulnerability 2: Negative Trade Value Bypass (`trade_value_usd < 0.0`)
- **Direct Observation**:
  Executing `pipeline.evaluate(req)` with `trade_value_usd = -100.0` returns:
  `GuardrailVerdict(approved=True, simulated_gas_used=145000, quoted_amount_out_min=9994823000000000, estimated_price_impact_pct=0.00177)`.
- **Root Cause**:
  `-100.0 > 250.0` evaluates to `False`. The portfolio concentration calculation becomes `(400.0 + (-100.0)) / 5000.0 = 6.0% <= 20.0%`, which passes. In Layer 4, `gas_ratio_pct = (gas_cost_usd / -100.0) * 100.0` produces a negative percentage (e.g. `-0.06%`), which satisfies `<= 1.5%`. Dry-run simulation executes successfully, leading to an unwarranted `approved=True`.
- **Architectural Placement**:
  `Layer 2: Capital Allocation`. Negative trade values must be blocked by the same check as zero trade value: `if request.trade_value_usd <= 0.0:`.

### Vulnerabilities 3 & 4: Zero & Negative Token Amount (`amount_in_wei <= 0`)
- **Direct Observation**:
  Calling `pipeline.evaluate(req)` with `amount_in_wei = 0` or `amount_in_wei = -10**16` returns `approved=True`.
- **Root Cause**:
  The pipeline never verifies `amount_in_wei > 0`. The mock quoter returns 0 output for 0 input with 0.0% price impact, gas ratio passes against `trade_value_usd`, and the simulation executes without error.
- **Architectural Placement**:
  `Layer 2: Capital Allocation`. Token quantities must be strictly positive integers.

### Vulnerability 5: ZeroDivisionError on Zero Portfolio Value (`current_portfolio_value_usd = 0.0`)
- **Direct Observation**:
  Calling `pipeline.evaluate(req, current_portfolio_value_usd=0.0)` raises:
  `ZeroDivisionError: float division by zero` in `execution/guardrails/pipeline.py:139`:
  `concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0`
- **Root Cause**:
  The concentration calculation assumes `current_portfolio_value_usd > 0.0`. An uninitialized account or portfolio reporting zero balance triggers an unhandled crash.
- **Architectural Placement**:
  `Layer 2: Capital Allocation`. A trade cannot be evaluated against an empty or negative portfolio; it must be rejected with `Layer 2: Capital Allocation`. Defensively, line 139 must also guard against division by zero.

### Vulnerability 6: Non-Positive or Expired Deadline (`deadline_seconds < 1`)
- **Direct Observation**:
  Calling `pipeline.evaluate(req)` with `deadline_seconds = -10` returns `approved=True`.
- **Root Cause**:
  Line 179 only checks `if request.deadline_seconds > 300:`. Non-positive deadlines (e.g. `-10`, `0`) pass Layer 3. When converted to a UNIX timestamp by the router (`int(time.time()) + request.deadline_seconds`), the resulting timestamp is in the past, guaranteeing an EVM revert on-chain (`Transaction too old`) and wasting user gas.
- **Architectural Placement**:
  `Layer 3: Dynamic Slippage`. Must enforce `request.deadline_seconds >= 1`.
  *Important Note*: Existing test `test_m2_adversarial_challenge.py:676` explicitly checks for `"deadline 301s exceeds 300s limit"` when `deadline_seconds > 300`. Therefore, the `< 1` check must be distinct from the `> 300` check to avoid altering the rejection message of the existing upper-bound check.

### Vulnerability 7: Negative Slippage Tolerance (`slippage_bps < 0`)
- **Direct Observation**:
  Calling `pipeline.evaluate(req)` with `slippage_bps = -50` returns `approved=True`.
- **Root Cause**:
  Line 157 only checks `if request.slippage_bps > self.config.max_slippage_bps:`. Negative slippage passes Layer 3.
- **Architectural Placement**:
  `Layer 3: Dynamic Slippage`. Must enforce `request.slippage_bps >= 0`.
  *Important Note*: Existing test `test_m2_adversarial_challenge.py:660` checks for `"Requested slippage 101 bps exceeds max 100"` when `slippage_bps > 100`. Therefore, the `< 0` check must be distinct from the `> max_slippage_bps` check to preserve the existing rejection message format.

### Vulnerability 8: Self-Swaps (`request.token_in.lower() == request.token_out.lower()`)
- **Direct Observation**:
  Calling `pipeline.evaluate(req)` where `token_in == token_out` returns `approved=True`.
- **Root Cause**:
  Layer 1 inspects each token's GoPlus security status independently but never checks whether `token_in` and `token_out` are the same asset.
- **Architectural Placement**:
  `Layer 1: Contract Security`. Swapping an asset for itself is a no-op that burns gas and swap fees without altering portfolio allocation.

---

## 3. The "0xSafe" Test Fixture Trap Discovery

During the cross-suite audit, we evaluated how the proposed fixes impact all 6 test suites across the project:
1. `tests/unit/test_execution.py` (35 tests)
2. `tests/e2e/test_tier1_f08_f14_wallet_guardrails.py` (35 tests)
3. `tests/e2e/run_all.py` (200 tests across Tiers 1-4)
4. `tests/adversarial/test_m2_guardrails_adversarial.py` (32 tests)
5. `tests/adversarial/test_m2_adversarial_challenge.py` (26 tests)

### The Discovery:
In `tests/adversarial/test_m2_adversarial_challenge.py`, `teamwork_challenger_m2_2` filed Challenge 5 demanding that `token_in == token_out` be rejected in Layer 1.
However, in lines 578–745 of that same file, the author constructed dummy `SwapTransactionRequest` fixtures with:
```python
token_in = "0xSafe"
token_out = "0xSafe"
```
Specifically in:
- Line 580: `req_250` (tests exact $250.00 spend cap boundary)
- Line 592: `req_250_01` (tests $250.01 spend cap rejection)
- Line 620: `req_small` (tests 7.99% and 8.00% drawdown boundaries)
- Line 637: `req_slip_100` (tests 100 bps slippage boundary)
- Line 650: `req_slip_101` (tests 101 bps slippage rejection)
- Line 666: `req_dl_301` (tests 301s deadline rejection)
- Line 688: `req` (tests gas ceiling and gas ratio boundaries)
- Line 720: `req` (tests simulation revert message decoding)

If `pipeline.py` rejects `token_in.lower() == request.token_out.lower()` in Layer 1, then:
- `test_layer2_capital_allocation_exact_boundaries` will fail at line 587 (`assert guardrail_pipeline.evaluate(req_250).approved is True`) because it gets rejected at Layer 1!
- `test_layer3_slippage_and_deadline_boundaries` will fail at line 645 (`assert guardrail_pipeline.evaluate(req_slip_100).approved is True`)!
- `test_layer4_gas_boundaries` will fail at line 707 (`assert v_ratio_pass.approved is True`)!

### Resolution:
In `tests/adversarial/test_m2_adversarial_challenge.py`, those 8 fixture instances must be updated to use distinct dummy addresses:
- `token_in = "0xSafeIn"`
- `token_out = "0xSafeOut"`

Because `MockGoPlusClient` treats any unknown address as a safe token, `0xSafeIn` and `0xSafeOut` pass Layer 1 cleanly, allowing the exact boundary logic for Layers 2, 3, 4, and 5 to execute and pass as intended.

---

## 4. Proposed Fix Specification (for Worker Implementation)

### File 1: `execution/guardrails/pipeline.py`

#### Change 1: Layer 1 Token Distinctness (Lines 98–104)
Add before `sec_in = self.goplus.check_token_security(...)`:
```python
        # Self-swap validation
        if request.token_in.lower() == request.token_out.lower():
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 1: token_in and token_out cannot be the same address.",
                layer_failed="Layer 1: Contract Security",
            )
```

#### Change 2: Layer 2 Lower Bounds & Positive Values (Lines 131–146)
Replace lines 131–146 with:
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

        if request.trade_value_usd > self.max_spend_per_trade_usd:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Per-trade spend ${request.trade_value_usd} exceeds cap of ${self.max_spend_per_trade_usd}.",
                layer_failed="Layer 2: Capital Allocation",
            )

        new_asset_total = current_asset_holdings_usd + request.trade_value_usd
        concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0 if current_portfolio_value_usd > 0.0 else 100.0
        if concentration_pct > self.max_asset_concentration_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Asset concentration {concentration_pct:.1f}% exceeds max {self.max_asset_concentration_pct}%.",
                layer_failed="Layer 2: Capital Allocation",
            )
```

#### Change 3: Layer 3 Non-Negative Slippage & Minimum Deadline (Lines 157–185)
Update Layer 3 checks:
```python
        if request.slippage_bps < 0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Requested slippage {request.slippage_bps} bps cannot be negative.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.slippage_bps > self.config.max_slippage_bps:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Requested slippage {request.slippage_bps} bps exceeds max {self.config.max_slippage_bps} bps.",
                layer_failed="Layer 3: Dynamic Slippage",
            )
```
And for deadline:
```python
        if request.deadline_seconds < 1:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Transaction deadline {request.deadline_seconds}s must be at least 1 second.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.deadline_seconds > 300:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Transaction deadline {request.deadline_seconds}s exceeds 300s limit.",
                layer_failed="Layer 3: Dynamic Slippage",
            )
```

#### Change 4: Layer 4 Defensive Zero-Division Guard (Line 201)
Update gas ratio calculation to be mathematically safe under all conditions:
```python
        simulated_gas = 145000
        gas_cost_usd = (simulated_gas * (base_fee_gwei + priority_fee_gwei) * 1e-9) * self.eth_price_usd
        gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0 if request.trade_value_usd > 0.0 else float("inf")
```

---

### File 2: `tests/adversarial/test_m2_adversarial_challenge.py`

Update dummy token addresses in lines 580, 592, 620, 637, 650, 666, 688, 720 from `token_in="0xSafe"`, `token_out="0xSafe"` to:
```python
token_in = "0xSafeIn"
token_out = "0xSafeOut"
```
This aligns the test fixtures with the challenger's own specification requiring distinct token addresses for cross-token swaps.

---

## 5. Verification Plan

After the worker applies these modifications, verify that 100% of all suites pass:

1. **Adversarial Hardening Suite (Target: 32/32 PASS)**:
   ```powershell
   python -m pytest "tests/adversarial/test_m2_guardrails_adversarial.py" -v
   ```
2. **Adversarial Verification Suite (Target: 26/26 PASS)**:
   ```powershell
   python -m pytest "tests/adversarial/test_m2_adversarial_challenge.py" -v
   ```
3. **Execution Subsystem Unit Suite (Target: 35/35 PASS)**:
   ```powershell
   python -m pytest "tests/unit/test_execution.py" -v
   ```
4. **Tier 1 Feature Verification Suite (Target: 35/35 PASS)**:
   ```powershell
   python -m pytest "tests/e2e/test_tier1_f08_f14_wallet_guardrails.py" -v
   ```
5. **Full Platform E2E Runner (Target: 200/200 PASS)**:
   ```powershell
   python tests/e2e/run_all.py
   ```
Total across all execution & adversarial suites: **328 / 328 passing tests (100% green)**.
