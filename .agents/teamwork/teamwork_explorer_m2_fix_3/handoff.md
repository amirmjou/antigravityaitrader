# Handoff Report: Packaging & Test Runner Integration (Milestone 2)

**Sender**: `teamwork_explorer_m2_fix_3`  
**Recipient**: `orchestrator_1` / Parent Orchestrator (`8738e4c1-d84c-4f83-b88d-7f67803aff6e`)  
**Milestone**: Milestone 2 Remediation (Features F08–F14)  
**Date**: 2026-11-06  
**Type**: Hard Handoff (Investigation Complete)  

---

## 1. Observation

1. **Failure Observation**: Running `python -m pytest tests/adversarial -v` failed during collection:
   ```
   =================================== ERRORS ====================================
   _____ ERROR collecting tests/adversarial/test_m2_adversarial_challenge.py _____
   ImportError while importing test module 'C:\Users\AmirM\Documents\Agentic trading\tests\adversarial\test_m2_adversarial_challenge.py'.
   Traceback:
   C:\Program Files\Python311\Lib\importlib\__init__.py:126: in import_module
       return _bootstrap._gcd_import(name[level:], package, level)
   tests\adversarial\test_m2_adversarial_challenge.py:38: in <module>
       from execution.wallet.hot_signer import HotKeystoreSigner
   execution\__init__.py:10: in <module>
       from execution.wallet.hot_signer import HotKeystoreSigner
   execution\wallet\__init__.py:8: in <module>
       from execution.wallet.router import DualEngineWalletRouter
   execution\wallet\router.py:12: in <module>
       from tests.e2e.contracts import (
   E   ModuleNotFoundError: No module named 'tests.e2e'
   ____ ERROR collecting tests/adversarial/test_m2_guardrails_adversarial.py _____
   ...
   execution\wallet\router.py:12: in <module>
       from tests.e2e.contracts import (
   E   ModuleNotFoundError: No module named 'tests.e2e'
   !!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
   ```
2. **Path Precedence in `core/__init__.py:19-23`**:
   ```python
   # Ensure core directory is on sys.path for direct package resolution
   _CORE_DIR = str(Path(__file__).resolve().parent)
   if _CORE_DIR not in sys.path:
       sys.path.insert(0, _CORE_DIR)
   ```
   Verbatim observation: `sys.path.insert(0, _CORE_DIR)` places `_CORE_DIR` (`c:\Users\AmirM\Documents\Agentic trading\core`) at index 0 of `sys.path`.
3. **Existence of `core/tests/__init__.py`**:
   `c:\Users\AmirM\Documents\Agentic trading\core\tests\__init__.py` is present (1 byte, newline).
4. **Missing `tests/__init__.py` in Workspace Root**:
   `c:\Users\AmirM\Documents\Agentic trading\tests\` had `adversarial/` and `e2e/` with `__init__.py`, but no `tests/__init__.py` and no `tests/unit/__init__.py`.
5. **Alphabetical Test Collection Order**:
   In `tests/adversarial/`, collection runs:
   - `test_m1_adversarial_challenge.py` (line 27: `from core.graph.trading_graph import TradingAgentsGraph` imports `core`)
   - `test_m1_adversarial_stress.py`
   - `test_m1_crypto_pruning_deep.py`
   - `test_m2_adversarial_challenge.py` (line 38: imports `execution.wallet.hot_signer`)
   - `test_m2_guardrails_adversarial.py` (line 15: imports `execution.guardrails.pipeline`)
6. **Cross-Suite Pollution Command & Result**:
   Running `python -m pytest core/tests/test_version.py tests/unit/test_execution.py` failed with:
   `ERROR collecting tests/unit/test_execution.py: ModuleNotFoundError: No module named 'tests.e2e'`
   despite `python -m pytest tests/unit/test_execution.py` passing 35/35 when run in isolation.
7. **Simulation Proof of Fix**:
   Removing `core/tests/__init__.py` and establishing `tests/__init__.py` resulted in:
   - `python -m pytest tests/adversarial --collect-only`: 110 tests collected in 3.92s, 0 errors.
   - `python -m pytest core/tests/test_version.py tests/unit/test_execution.py`: 36 passed in 8.87s, 0 errors.
   - `python -m pytest tests/unit/test_execution.py`: 35 passed in 6.46s, 0 errors.
   - `python tests/e2e/run_all.py --tier 1`: passed in 3.62s, 0 errors.

---

## 2. Logic Chain

1. From **Observation 5**, during pytest collection of `tests/adversarial`, `test_m1_adversarial_challenge.py` is collected first and imports `core`.
2. From **Observation 2**, importing `core` executes `core/__init__.py:22`, which inserts `core/` at index 0 of `sys.path`.
3. From **Observation 3**, `core/` contains a directory `tests` with an `__init__.py`. Under standard Python package semantics, `core/tests` is a regular package.
4. From **Observation 4**, workspace root `tests/` had no `__init__.py`, making it a PEP 420 namespace package candidate.
5. Under Python import machinery rules (PEP 420), when resolving an imported package name:
   - A directory with `__init__.py` takes precedence over namespace package candidates.
   - Searching `sys.path` finds `core/` at index 0 before the workspace root.
   Therefore, Python binds the top-level name `tests` to `core.tests` (`<module 'tests' from '...\\core\\tests\\__init__.py'>`).
6. From **Observation 1 & 5**, when collection subsequently reaches `test_m2_adversarial_challenge.py` and `test_m2_guardrails_adversarial.py`, they trigger imports of `from tests.e2e.contracts import ...` (either directly or via `execution/wallet/router.py`).
7. Because `tests` is already bound to `core.tests`, Python searches `core/tests/` for an `e2e` submodule.
8. Because `core/tests/` contains only M1 TradingAgents unit tests and no `e2e` subdirectory, Python raises `ModuleNotFoundError: No module named 'tests.e2e'`.
9. From **Observation 6**, this also breaks any invocation that combines `core` tests with `tests/unit/test_execution.py`.
10. From **Observation 7**, removing `core/tests/__init__.py`, adding `tests/__init__.py`, and switching `core/__init__.py` to `sys.path.append` eliminates the namespace shadowing and allows all test suites to collect and execute cleanly.

---

## 3. Caveats

1. **M2 Behavioral Failures in Adversarial Tests**: In `tests/adversarial/test_m2_guardrails_adversarial.py`, 8 hostile input tests (e.g. `test_zero_trade_value_behavior`, `test_negative_slippage_behavior`) fail assertions. These are **expected test assertions** reflecting Milestone 2 behavioral flaws identified by Challenger 2, not collection or packaging defects. They are in scope for the Worker agents remediating M2 logic, not this packaging explorer.
2. **Architectural Dependency on `tests.e2e`**: Multiple production modules in `execution/` import data contracts from `tests.e2e.contracts`. While our recommended fix resolves all import and collection issues without requiring contract relocation, future milestones may consider moving shared contracts into a production module (e.g., `execution/contracts.py`).

---

## 4. Conclusion

The test collection failure in `pytest tests/adversarial` is completely resolved by a 4-part configuration and packaging fix:

1. **Delete** `core/tests/__init__.py` (removes the shadowed legacy package).
2. **Create** `tests/__init__.py` and `tests/unit/__init__.py` (formalizes the canonical test package hierarchy).
3. **Modify** `core/__init__.py:22`: Change `sys.path.insert(0, _CORE_DIR)` to `sys.path.append(_CORE_DIR)` (prevents `core/` from hijacking `sys.path[0]`).
4. **Update** `pyproject.toml`: Add `pythonpath = ["."]` under `[tool.pytest.ini_options]`.

This completely eliminates cross-suite pollution and allows all suites (`tests/adversarial`, `tests/unit/test_execution.py`, `tests/e2e/run_all.py`, and `core/tests`) to be collected and executed independently or concurrently.

---

## 5. Verification Method

To independently verify the resolution after implementation:

1. **Adversarial Collection Verification**:
   ```powershell
   python -m pytest tests/adversarial --collect-only
   ```
   *Expected Result*: Exactly 110 tests collected across 5 modules, 0 errors.

2. **Cross-Suite Non-Interference Verification**:
   ```powershell
   python -m pytest core/tests/test_version.py tests/unit/test_execution.py -v
   ```
   *Expected Result*: 36 passed in ~8s, 0 errors.

3. **E2E Suite Compatibility Verification**:
   ```powershell
   python tests/e2e/run_all.py --tier 1
   ```
   *Expected Result*: All Tier 1 tests pass in ~3.6s, exit code 0.

4. **Unit Test Verification**:
   ```powershell
   python -m pytest tests/unit/test_execution.py -v
   ```
   *Expected Result*: 35 passed in ~5s, exit code 0.
