# Dispatch Assignment: Milestone 2 Remediation Worker (Iteration 2)

## Mission
Implement the complete remediation package for Milestone 2 (MetaMask Wallet Integration & 6-Layer Safety Guardrails) to resolve all 8 adversarial failure modes, align the "0xSafe" test fixtures, and resolve the `sys.path` package shadowing issue.

## 🔒 Mandatory Integrity Warning
> DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Mandatory Context
Read `ORIGINAL_REQUEST.md` verbatim before beginning:
`c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md`

Read `PROJECT.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\PROJECT.md`

## Input Evidence & Explorer Specifications
Study the comprehensive analysis and handoff reports prepared by the 3 Explorers:
1. **Input Sanitization & Division Hardening**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_1\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_1\handoff.md`
2. **Test Suite Compatibility Matrix**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_2\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_2\handoff.md`
3. **Packaging & sys.path Resolution**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_3\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m2_fix_3\handoff.md`

## Implementation Tasks

### Task 1: Packaging & Import Precedence Fix
1. Delete `core/tests/__init__.py` (stops package shadowing of workspace `tests/`).
2. Create `tests/__init__.py` and `tests/unit/__init__.py`.
3. In `core/__init__.py:22`: Change `sys.path.insert(0, _CORE_DIR)` to `sys.path.append(_CORE_DIR)`.
4. In `pyproject.toml`: Add `pythonpath = ["."]` under `[tool.pytest.ini_options]`.

### Task 2: Input Sanitization & Division Hardening in `PreBroadcastGuardrailPipeline`
Apply drop-in fixes to `execution/guardrails/pipeline.py` (and mirror in `tests/e2e/harness.py`):
1. **Layer 1 (Contract Security)**:
   - Self-swap check: If `request.token_in.lower() == request.token_out.lower()`, return `approved=False, layer_failed=1, rejection_reason="Layer 1: Self-swap rejected - token_in and token_out cannot be the same asset"`.
   - Positive amount check: If `request.amount_in_wei <= 0`, return `approved=False, layer_failed=1, rejection_reason="Layer 1: Non-positive amount_in_wei rejected - amount must be > 0"`.
2. **Layer 2 (Capital Allocation)**:
   - Strictly positive trade value: If `request.trade_value_usd <= 0.0`, return `approved=False, layer_failed=2, rejection_reason="Layer 2: Non-positive trade_value_usd rejected - trade value must be > $0.00"`.
   - Strictly positive portfolio value: If `current_portfolio_value_usd <= 0.0`, return `approved=False, layer_failed=2, rejection_reason="Layer 2: Non-positive portfolio value rejected - current portfolio value must be > $0.00"`.
   - Defensive division guard at line 139: Guard `concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0 if current_portfolio_value_usd > 0 else 100.0`.
3. **Layer 3 (Dynamic Slippage)**:
   - Negative slippage check: If `request.slippage_bps < 0`, return `approved=False, layer_failed=3, rejection_reason="Layer 3: Negative slippage tolerance rejected"`. Keep existing `request.slippage_bps > self.config.max_slippage_bps` check intact to preserve error messages.
   - Non-positive / expired deadline check: If `request.deadline_seconds < 1`, return `approved=False, layer_failed=3, rejection_reason="Layer 3: Non-positive deadline rejected"`. Keep existing `request.deadline_seconds > 300` check intact to preserve error messages.
4. **Layer 4 (Gas & Liquidity)**:
   - Defensive division guard at line 201: Guard `gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0 if request.trade_value_usd > 0 else float('inf')`.

### Task 3: Test Fixture Alignment in `tests/adversarial/test_m2_adversarial_challenge.py`
In `tests/adversarial/test_m2_adversarial_challenge.py`, update the 8 test requests that erroneously used `token_in="0xSafe", token_out="0xSafe"` (self-swaps) at lines 580, 592, 620, 637, 650, 666, 688, 720:
Change `token_out="0xSafe"` to `token_out="0xSafeOut"`.

## Verification Commands (Must all pass 100%)
1. `python -m pytest "tests/adversarial/test_m2_guardrails_adversarial.py" -v` -> Target: 32/32 PASSED.
2. `python -m pytest "tests/adversarial/test_m2_adversarial_challenge.py" -v` -> Target: 26/26 PASSED.
3. `python -m pytest "tests/adversarial/" -v` -> Target: 110/110 PASSED.
4. `python -m pytest "tests/unit/test_execution.py" -v` -> Target: 35/35 PASSED.
5. `python -m pytest "tests/e2e/test_tier1_f08_f14_wallet_guardrails.py" -v` -> Target: 35/35 PASSED.
6. `python tests/e2e/run_all.py` -> Target: 200/200 PASSED across Tiers 1-4.
7. `python -m pytest "core/tests/" -q` -> Target: All core tests PASSED.

Document all commands, stdout/stderr, and exit codes in `handoff.md` and send a completion message back.

## 2026-11-06T19:11:52Z
[Message] timestamp=2026-11-06T19:11:52Z sender=8738e4c1-d84c-4f83-b88d-7f67803aff6e priority=MESSAGE_PRIORITY_HIGH
You are teamwork_worker_m2_2, the Milestone 2 Remediation Worker.
Your working directory is c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m2_2\
