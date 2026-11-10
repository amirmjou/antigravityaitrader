# Changes Inventory — Milestone 1 Iteration 2 Remediation

## Overview
This document details all modifications performed by `teamwork_worker_m1_2` to resolve the 21 core test failures and implement Fix Strategy 1 (Float/NaN/Inf Sanitization & Jev Hardening), Fix Strategy 2 (Crypto Pruning & Prompt Isolation), and Fix Strategy 3 (Core Test Infrastructure & Fixture Realignment).

All modifications strictly respect the assigned write boundaries:
- `core/`
- `tests/adversarial/`
- `.agents/teamwork/teamwork_worker_m1_2/`
No files within `execution/`, `visualization/`, `crypto_pipeline/`, or `tests/e2e/` were modified.

---

## Modified Files

### 1. `core/__init__.py`
- **Rationale**: Resolved module bifurcation where importing `tradingagents` vs native modules loaded separate module objects and broke function identity checks (`cli.selections.get_ticker is cli.prompts.get_ticker`).
- **Changes**:
  - Ensured `_CORE_DIR` is present at the front of `sys.path`.
  - Streamlined `_TradingAgentsAliasFinder` to avoid reloading or modifying `sys.modules` once resolved.

### 2. `core/tests/conftest.py`
- **Rationale**: Prevented premature import of `core` before test environment isolation, which had caused `DEFAULT_CONFIG` to freeze with user directory paths (`~/.tradingagents`) instead of isolated temporary fixtures.
- **Changes**:
  - Moved `import core` and `import core.default_config` inside fixture setup after `_own_file_locations()` executes.
  - Added programmatic rebuild of `DEFAULT_CONFIG = build_default_config()`.
  - Patched `_PREFS_PATH` in `cli.prefs` and `core.cli.prefs` to temporary test directory.

### 3. `core/tests/test_i18n_coverage.py`
- **Rationale**: The test was looking for `tradingagents/agents` instead of `core/agents`.
- **Changes**:
  - Updated `_AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"`.

### 4. `core/tests/test_reporting.py` & `core/tests/test_sec_edgar.py`
- **Rationale**: Tests referenced `tradingagents.__version__`, which was undefined.
- **Changes**:
  - Referenced `core.__version__` safely.

### 5. `core/tests/test_cli_commands.py`
- **Rationale**: Subprocess invocations of `cli.main` failed when running outside package root without `PYTHONPATH`.
- **Changes**:
  - Added `import sys` and injected `core_dir` into the child process `env["PYTHONPATH"]`.

### 6. `core/agents/schemas.py`
- **Rationale**: Fix Strategy 1 required rejecting non-finite floats (`NaN`, `Infinity`, non-finite strings) across Pydantic schemas, coercing nullish strings to `None`, and enforcing strict RFC 8259 JSON compliance.
- **Changes**:
  - Expanded `_NULLISH_FLOAT` set with `{"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}`.
  - Hardened `_coerce_optional_float` to reject `math.isnan(v)` and `math.isinf(v)`.
  - Added `model_config = ConfigDict(allow_inf_nan=False, validate_assignment=True)` to `TraderProposal`, `PortfolioDecision`, and `SentimentReport`.
  - Added field validators on `entry_price`, `stop_loss`, and `position_size` to guarantee strictly positive finite floats or `None`.

### 7. `core/agents/jev_adapter.py`
- **Rationale**: Fix Strategy 1 required preventing adversarial bypasses of Jev decision-making via `NaN` / `Infinity` in price fields, unanchored stop orders, and graceful handling of empty variants/criteria.
- **Changes**:
  - In `evaluate_choice` and `pick_variant`, handled empty criteria/variants gracefully returning `probs = {}` without calling `max()`.
  - In `score_trader_proposal()`, enforced `math.isfinite()` on both `entry_price` and `stop_loss`.
  - Enforced that unanchored stop orders (`has_stop and not has_entry`) are flagged as invalid (`stop_valid = False`), failing approval.

### 8. `core/agents/analysts/fundamentals_analyst.py`
- **Rationale**: Fix Strategy 2 required guaranteeing zero corporate data leakage or execution on crypto assets.
- **Changes**:
  - Added an early skip guard checking `ticker` against `_CRYPTO_BASES` or `asset_type == "crypto"`, immediately returning `{"messages": [], "fundamentals_report": ""}`.

### 9. `core/agents/researchers/bull_researcher.py` & `core/agents/researchers/bear_researcher.py`
- **Rationale**: Fix Strategy 2 required suppressing corporate fundamentals text from LLM debate prompts for crypto assets.
- **Changes**:
  - Checked `is_crypto` on asset/ticker. If crypto, completely suppressed the fundamentals section and provided crypto-specific protocol metrics, tokenomics, on-chain volume, and TVL focus directives.
  - Preserved `get_language_instruction()` formatting.

### 10. `core/graph/trading_graph.py`
- **Rationale**: Fix Strategy 2 & graph architectural resilience required compiling a specialized `crypto_workflow` that completely prunes the `fundamentals` analyst node from the execution DAG.
- **Changes**:
  - Added `self.crypto_workflow` in `__init__` constructed without the fundamentals analyst node.
  - Added helper methods `_is_crypto()`, `_active_analysts()`, and `get_workflow()`.
  - Dynamically switched between `self.crypto_workflow` and `self.workflow` based on ticker / asset type.
  - Updated `begin_checkpoint` and `end_checkpoint` to handle mock instances (`getattr(self, "workflow", None)`) and preserve disabled checkpointing semantics for equity runs.

### 11. `tests/adversarial/test_m1_adversarial_challenge.py`
- **Rationale**: Aligned assertions with the hardened system behaviors (RFC 8259 NaN->None sanitization, Jev NaN rejection, crypto fundamentals suppression).
- **Changes**:
  - Verified `p.entry_price is None` when initialized with `float("nan")`.
  - Verified RFC 8259 strict JSON serialization succeeds without non-finite float tokens.
  - Verified `score["approved"] is False` when proposal contains non-finite entries.
  - Verified `crypto_workflow` DAG contains exactly `["market", "sentiment", "news"]` and excludes `fundamentals`.

### 12. `tests/adversarial/test_m1_adversarial_stress.py`
- **Rationale**: Aligned assertions with the hardened Jev adapter and schema validation behavior.
- **Changes**:
  - Updated assertions for empty variant scoring to match graceful empty dictionary return.
  - Updated negative/zero stop-loss assertion to verify proper rejection (`stop_valid=False`, `approved=False`).

---

## Verification Results Summary
- `python -m pytest "core/tests/" -q` -> **1420 passed, 6 skipped, 1 deselected, 24 warnings, 100 subtests passed (0 failures)**
- `python -m pytest "tests/adversarial/test_m1_adversarial_challenge.py" -v` -> **9 passed (0 failures)**
- `python -m pytest "tests/adversarial/test_m1_adversarial_stress.py" -v` -> **39 passed (0 failures)**
- `python tests/e2e/run_all.py` -> **200 passed (0 failures)**
