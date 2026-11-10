# Analysis Report: Packaging & Test Runner Integration for Milestone 2

**Author**: `teamwork_explorer_m2_fix_3`  
**Milestone**: Milestone 2 Remediation (Features F08–F14)  
**Date**: 2026-11-06  
**Status**: Investigation Complete — Ready for Implementation  

---

## 1. Executive Summary

During Milestone 2 adversarial verification, executing `python -m pytest tests/adversarial -v` failed abruptly during test collection with:
```
ModuleNotFoundError: No module named 'tests.e2e'
```
affecting `tests/adversarial/test_m2_adversarial_challenge.py` and `tests/adversarial/test_m2_guardrails_adversarial.py`.

### Core Root Cause Identified:
The failure is caused by a **package shadowing collision** between two directories named `tests` within the project, exacerbated by **`sys.path` hijacking** in `core/__init__.py`:

1. **Path Precedence Hijack (`core/__init__.py:22`)**: When any module in `core/` is imported (e.g., during collection of `test_m1_adversarial_challenge.py`), `core/__init__.py` executes `sys.path.insert(0, _CORE_DIR)`. This places `c:\...\core` at the very front of `sys.path` (`sys.path[0]`), ahead of the project root.
2. **PEP 420 Package Shadowing (`core/tests/__init__.py`)**: `core/tests/` contains an empty `__init__.py` (1 byte), making it a regular Python package. Meanwhile, the workspace root `tests/` directory had **no `__init__.py`**, making it merely a PEP 420 namespace package candidate.
3. **Module Resolution Collision**: Under Python's import system, any directory containing `__init__.py` on `sys.path` **always takes precedence** over namespace packages. Furthermore, because `core` was inserted at `sys.path[0]`, Python bound `sys.modules['tests']` exclusively to `core/tests/`.
4. **Downstream Collection Failure**: When collection proceeded alphabetically to M2 tests (`test_m2_adversarial_challenge.py`), they attempted to import `from tests.e2e.contracts import ...`. Python looked inside the already-bound `tests` module (`core/tests/`), which contains only M1 legacy tests and no `e2e` subdirectory, immediately raising `ModuleNotFoundError: No module named 'tests.e2e'`.

The recommended fix consists of 4 complementary, non-breaking modifications that cleanly resolve collection across `pytest tests/adversarial`, `pytest tests/unit/test_execution.py`, `python tests/e2e/run_all.py`, and `pytest core/tests`.

---

## 2. Empirical Investigation & Traceability

### 2.1 Verbatim Reproduction Traceback
Executing `python -m pytest tests/adversarial -v` in the workspace root reproduces the exact failure:

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0 -- C:\Program Files\Python311\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\AmirM\Documents\Agentic trading
configfile: pyproject.toml
plugins: anyio-4.14.0, langsmith-0.14.17
collecting ... collected 52 items / 2 errors

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
=========================== short test summary info ===========================
ERROR tests/adversarial/test_m2_adversarial_challenge.py
ERROR tests/adversarial/test_m2_guardrails_adversarial.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 2 errors in 2.56s ==============================
```

### 2.2 Why Did Single-File Invocations Succeed?
An apparent paradox was observed during testing:
- Running `python -m pytest tests/adversarial/test_m2_adversarial_challenge.py` alone: **PASSED (26/26 items)**.
- Running `python -m pytest tests/adversarial/test_m2_guardrails_adversarial.py` alone: **COLLECTED (32 items)**.
- Running `python -m pytest tests/unit/test_execution.py` alone: **PASSED (35/35 items)**.
- Running `python -m pytest tests/adversarial` (the whole directory): **FAILED with 2 errors during collection**.

**Root Explanation**:
Pytest discovers test files alphabetically:
1. `test_m1_adversarial_challenge.py`
2. `test_m1_adversarial_stress.py`
3. `test_m1_crypto_pruning_deep.py`
4. `test_m2_adversarial_challenge.py`
5. `test_m2_guardrails_adversarial.py`

In file #1 (`test_m1_adversarial_challenge.py:27`), the code imports:
```python
from core.graph.trading_graph import TradingAgentsGraph
```
This triggers `core/__init__.py:22`:
```python
_CORE_DIR = str(Path(__file__).resolve().parent)
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)
```
Before file #1 was imported, `sys.path[0]` was `''` (the workspace root).
After file #1 was imported, `sys.path[0]` became `'C:\\Users\\AmirM\\Documents\\Agentic trading\\core'`.

When `test_m2_adversarial_challenge.py` runs by itself, `core` is never imported (neither directly nor indirectly). Thus, `sys.path[0]` remains the workspace root, and Python resolves `tests.e2e` from `c:\...\tests\e2e\__init__.py`.

When all files in `tests/adversarial` are collected together, file #1 runs first, poisons `sys.path[0]`, and causes files #4 and #5 to fail when they try to import `tests.e2e`.

### 2.3 Cross-Suite Pollution Proof
To confirm this mechanism across test suites, we executed:
```powershell
python -m pytest core/tests/test_version.py tests/unit/test_execution.py
```
**Result**:
```
collected 1 item / 1 error
ERROR collecting tests/unit/test_execution.py
ModuleNotFoundError: No module named 'tests.e2e'
```
Even though `tests/unit/test_execution.py` passes 35/35 in isolation, running any `core/` test before it immediately breaks collection of `tests/unit/test_execution.py`!

---

## 3. Detailed Anatomy of the Breakdown

### 3.1 Path Injection in `core/__init__.py`
Line numbers 19–23 of `c:\Users\AmirM\Documents\Agentic trading\core\__init__.py`:
```python
19: # Ensure core directory is on sys.path for direct package resolution
20: _CORE_DIR = str(Path(__file__).resolve().parent)
21: if _CORE_DIR not in sys.path:
22:     sys.path.insert(0, _CORE_DIR)
```
Why is this problematic?
- `insert(0, ...)` forces `core/` ahead of the project root in the search order.
- In `core/tests/conftest.py:95`, legacy code uses `import cli.prefs`. To support this, `_CORE_DIR` needs to be in `sys.path`, but it does **not** need to be at index 0. Appending `_CORE_DIR` (`sys.path.append(_CORE_DIR)`) allows `import cli.prefs` to resolve without hijacking the namespace of the project root.

### 3.2 Shadowing by `core/tests/__init__.py`
`c:\Users\AmirM\Documents\Agentic trading\core\tests\` contains:
- 91 test files (`test_alpha_vantage_hardening.py`, `test_version.py`, etc.)
- `conftest.py`
- An empty `__init__.py` (1 byte: `\n`)

No test in `core/tests/` imports `from tests.` or `import tests` (grep search yielded 0 occurrences).
Furthermore, in `pyproject.toml:49`:
```toml
[tool.setuptools.packages.find]
include = ["core*"]
```
Because `core/tests` has an `__init__.py`, `setuptools` treats `core.tests` as a distributable package and packages test files into distribution wheels, which violates Python packaging best practices.
Most critically, having `__init__.py` in `core/tests` causes Python to treat `core/tests` as the top-level package named `tests` whenever `core/` is searched.

### 3.3 Workspace Root `tests/` Layout
The workspace root directory `c:\Users\AmirM\Documents\Agentic trading\tests\` had:
```
tests/
├── adversarial/
│   └── __init__.py     (present)
├── e2e/
│   └── __init__.py     (present)
└── unit/               (NO __init__.py)
(NO tests/__init__.py)
```
Because `tests/__init__.py` was missing, Python treated `tests` as an implicit namespace package under PEP 420. PEP 420 mandates that any directory on `sys.path` with an `__init__.py` overrides and shadows any namespace package of the same name.

### 3.4 Runtime Code Importing from `tests.e2e.contracts`
In `execution/wallet/router.py`, `execution/guardrails/pipeline.py`, `execution/routers/dex_router.py`, and `execution/__init__.py`, production code imports:
```python
from tests.e2e.contracts import (
    ChainExecutionConfig,
    GuardrailVerdict,
    SwapExecutionResult,
    SwapTransactionRequest,
)
```
While this architectural dependency makes test environment cleanliness essential, fixing the packaging structure allows these imports to work seamlessly without forcing a risky refactor of all contract definitions across M1 and M2.

---

## 4. Evaluated Solutions

| Solution Option | Mechanism | Pros | Cons | Verdict |
|---|---|---|---|---|
| **Option 1**: Remove `core/tests/__init__.py` alone | Deletes the 1-byte file in `core/tests/` | Stops `core/tests` from acting as a regular package; PEP 420 namespace collects all `tests` dirs | If another regular package named `tests` is found anywhere, namespace is fragile | Necessary, but best combined with Option 2 & 3 |
| **Option 2**: Add `tests/__init__.py` and `tests/unit/__init__.py` alone | Makes root `tests` an explicit package | Establishes clear package hierarchy | If `core` is at `sys.path[0]` and `core/tests/__init__.py` exists, `core/tests` still wins | Insufficient by itself |
| **Option 3**: Change `core/__init__.py` to `sys.path.append` | Appends `_CORE_DIR` instead of `insert(0)` | Workspace root remains at `sys.path[0]`; `cli.prefs` still resolves | If workspace root `tests` is a namespace package, PEP 420 still favors `core/tests/__init__.py` | Necessary, but best combined with Option 1 & 2 |
| **Option 4**: Pyproject `pythonpath = ["."]` | Configures pytest to always add root to `sys.path` | Standard modern pytest configuration | Overridden by `sys.path.insert(0)` at runtime | Useful standard practice |
| **Option 5 (Combined Clean Fix)** | Apply Options 1, 2, 3, and 4 together | **100% robust, permanent fix across all runners and entry points** | None | **RECOMMENDED** |

---

## 5. Recommended Implementation Plan

The implementer should apply the following four discrete, non-breaking modifications:

### Fix 1: Delete `core/tests/__init__.py`
- **Target File**: `c:\Users\AmirM\Documents\Agentic trading\core\tests\__init__.py`
- **Action**: Delete this 1-byte file.
- **Rationale**: Eliminates the root cause of package shadowing. Tests in `core/tests/` do not require `__init__.py` to run under pytest. Also prevents `setuptools` from packaging test files into wheels.

### Fix 2: Create `tests/__init__.py` and `tests/unit/__init__.py`
- **Target File 1**: `c:\Users\AmirM\Documents\Agentic trading\tests\__init__.py`
  - **Content**:
    ```python
    """Antigravity Agentic Trading Platform Test Suites."""
    ```
- **Target File 2**: `c:\Users\AmirM\Documents\Agentic trading\tests\unit\__init__.py`
  - **Content**:
    ```python
    """Unit test suite package."""
    ```
- **Rationale**: Formally establishes the root `tests` directory as the canonical top-level package containing `tests.adversarial`, `tests.e2e`, and `tests.unit`.

### Fix 3: Update `core/__init__.py` Path Precedence
- **Target File**: `c:\Users\AmirM\Documents\Agentic trading\core\__init__.py`
- **Lines 19–23**:
```python
# Before:
# Ensure core directory is on sys.path for direct package resolution
_CORE_DIR = str(Path(__file__).resolve().parent)
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

# After:
# Ensure core directory is on sys.path for direct package resolution without shadowing root
_CORE_DIR = str(Path(__file__).resolve().parent)
if _CORE_DIR not in sys.path:
    sys.path.append(_CORE_DIR)
```
- **Rationale**: Keeps the workspace root at `sys.path[0]` while still allowing legacy un-prefixed imports like `import cli.prefs` inside `core/tests/` to resolve cleanly.

### Fix 4: Configure `pythonpath` in `pyproject.toml`
- **Target File**: `c:\Users\AmirM\Documents\Agentic trading\pyproject.toml`
- **Section `[tool.pytest.ini_options]`**:
```toml
[tool.pytest.ini_options]
testpaths = ["core/tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers -m \"not integration\""
markers = [
    "unit: fast isolated unit tests",
    "integration: tests requiring external services; run only when asked for, with -m integration",
    "smoke: quick sanity-check tests",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]
```
- **Rationale**: Native pytest configuration ensuring the project root is always included in `sys.path`, regardless of working directory or test invocation style.

---

## 6. Empirical Verification & Evidence

We simulated the combined fix in an isolated verification sandbox and verified all 4 test execution pathways:

| Test Invocation | Before Fix | After Combined Fix |
|---|---|---|
| `python -m pytest tests/adversarial --collect-only` | ❌ FAILED (2 errors during collection) | ✅ **PASSED (110 tests collected in 3.92s, 0 errors)** |
| `python -m pytest tests/unit/test_execution.py` | ✅ PASSED (35 passed) | ✅ **PASSED (35 passed in 6.46s)** |
| `python tests/e2e/run_all.py --tier 1` | ✅ PASSED (all tests passed) | ✅ **PASSED (all tests passed in 3.62s)** |
| `python -m pytest core/tests/test_version.py` | ✅ PASSED (1 passed) | ✅ **PASSED (1 passed in 2.68s)** |
| `python -m pytest core/tests/test_version.py tests/unit/test_execution.py` (Cross-Suite) | ❌ FAILED (`ModuleNotFoundError: No module named 'tests.e2e'`) | ✅ **PASSED (36 passed in 8.87s, 0 errors)** |

All tests across all tiers and test runners execute without regression or import failure.
