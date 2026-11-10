# Adversarial Challenge Report: Milestone 1 (Multi-Agent Trading Architecture Integration)

**Challenger**: `teamwork_challenger_m1_2`  
**Roles**: Critic, Domain Specialist (Empirical Challenger)  
**Parent Orchestrator ID**: `8738e4c1-d84c-4f83-b88d-7f67803aff6e`  
**Date**: 2026-11-06  
**Empirical Harness**: `tests/adversarial/test_m1_adversarial_challenge.py` (9/9 tests executed and passed)  

---

## Challenge Summary

**Overall Risk Assessment**: **CRITICAL**  
**Explicit Verdict**: **REJECT / REQUEST_CHANGES**

While foundational multi-agent wiring, Jev offline heuristics determinism, and reflection settlement math on extreme price swings (+500%, -90%) are functional, independent empirical stress testing revealed three critical defect vectors that invalidate claims of production readiness and interface contract compliance:

1. **Crypto Fundamentals Pruning Failure & Deliberation Leakage**:
   - `TradingAgentsGraph.propagate("BTC-USD", asset_type="crypto")` fails to prune `Fundamentals Analyst` from the execution workflow. It executes unconditionally unless the caller manually filters analysts before building the graph.
   - If stale corporate equity statements exist in `state["fundamentals_report"]`, both `Bull Researcher` and `Bear Researcher` inject them directly into the crypto debate prompts.
2. **TraderProposal Numerical Sanity Breach & JevAdapter Safety Bypass**:
   - `TraderProposal` allows `NaN`, `Infinity`, `"-Infinity"`, `"nan"`, and `"Infinity"` to pass through validation as floats.
   - These values violate strict RFC 8259 JSON compliance (`json.dumps(..., allow_nan=False)` raises `ValueError`).
   - Worse, passing `entry_price=float('nan')` to `JevAdapter.score_trader_proposal()` exploits IEEE 754 comparison (`nan > 0` is `False`), causing `stop_valid` to default to `True` and resulting in Jev approving an invalid `entry_price=NaN` trade order.
3. **21 Test Failures in Core Package Test Suite**:
   - Running the full suite `python -m pytest "core/tests/"` revealed 21 test failures caused by unmigrated import paths (`tradingagents/agents` in `test_i18n_coverage.py`), undefined variables (`tradingagents.__version__`), and missing CLI subprocess module resolution.

---

## Challenges

### [Critical] Challenge 1: `TraderProposal` Leaks `NaN` and `Infinity`, Exploiting Jev Safety Gating

- **Assumption Challenged**: `TraderProposal` numerical fields (`entry_price`, `stop_loss`) are typed, sanitised, and guaranteed to be valid floats or `None`.
- **Attack Scenario**:
  An LLM emits `"NaN"` or `"Infinity"` when unable to compute price levels, or a upstream component injects `float("nan")`. In `core/agents/schemas.py:33-58`, `_coerce_optional_float` only coerces strings in `_NULLISH_FLOAT` (`"none"`, `"n/a"`, etc.) or ending in `"%"`:
  ```python
  if not isinstance(value, str):
      return value  # float('nan') and float('inf') are returned unchanged!
  ...
  try:
      return float(cleaned)  # float('nan') and float('Infinity') DO NOT raise ValueError in Python!
  ```
  When this proposal reaches `JevAdapter.score_trader_proposal()` (`core/agents/jev_adapter.py:237-248`):
  ```python
  has_stop = stop_loss is not None and stop_loss > 0
  has_entry = entry_price is not None and entry_price > 0
  if is_buy and has_entry and has_stop:
      stop_valid = stop_loss < entry_price
  ```
  Because `float('nan') > 0` evaluates to `False`, `has_entry` becomes `False`. The check `stop_loss < entry_price` is skipped, leaving `stop_valid = True`, and the order is **APPROVED**.
- **Blast Radius**:
  1. Downstream M2 guardrails perform arithmetic: `token_amount = allocation_usd / entry_price` -> produces `NaN` or `0.0`.
  2. Transaction serialization over strict JSON channels crashes (`ValueError: Out of range float values are not JSON compliant`).
  3. Risk management fails to reject unhedged / invalid orders.
- **Empirical Evidence**:
  Verified in `tests/adversarial/test_m1_adversarial_challenge.py::test_trader_proposal_numerical_leakage_nan` and `test_jev_adapter_nan_bypass_exploit`.
- **Recommended Mitigation**:
  Update `_coerce_optional_float` in `core/agents/schemas.py`:
  ```python
  def _coerce_optional_float(value):
      if value is None:
          return None
      if isinstance(value, (int, float)):
          return float(value) if math.isfinite(value) else None
      if not isinstance(value, str):
          return None
      text = value.strip().lower()
      if text in _NULLISH_FLOAT or text.endswith("%") or "nan" in text or "inf" in text:
          return None
      cleaned = text.replace(",", "").lstrip("$€£¥").strip()
      try:
          val = float(cleaned)
          return val if math.isfinite(val) else None
      except ValueError:
          return None
  ```
  In `JevAdapter.score_trader_proposal`:
  Explicitly verify `math.isfinite(entry_price)` and `math.isfinite(stop_loss)` before approving any proposal with specified levels.

---

### [Critical] Challenge 2: Crypto Asset Deliberation Fails to Prune Fundamentals Analyst in `TradingAgentsGraph`

- **Assumption Challenged**: Crypto assets (`BTC-USD`, `ETH-USD`, `SOL-USD`) automatically omit fundamentals analysis across all API entry points and prevent corporate financial statements from contaminating crypto deliberations.
- **Attack Scenario**:
  1. A caller invokes the programmatic API:
     ```python
     graph = TradingAgentsGraph()
     final_state, signal = graph.propagate("BTC-USD", "2026-04-18", asset_type="crypto")
     ```
     `TradingAgentsGraph.__init__` compiles the LangGraph workflow using `selected_analysts=("market", "social", "news", "fundamentals")`. When `propagate(..., asset_type="crypto")` is called, `self.graph` is invoked directly without rebuilding or bypassing the `Fundamentals Analyst` node.
     `Fundamentals Analyst` runs, queries equity-only tools (`get_fundamentals`, `get_balance_sheet`), and wastes compute/time.
  2. If `state["fundamentals_report"]` contains prior equity data (from cached state or previous ticker runs), lines 23-45 of `core/agents/researchers/bull_researcher.py` and `bear_researcher.py` format it as:
     `Asset fundamentals report (may be unavailable for crypto): <STALE 10-K INCOME STATEMENT>`
     The researchers read corporate PE ratios and balance sheet statements while debating Bitcoin!
- **Blast Radius**:
  Crypto trading decisions based on hallucinated or leaked corporate balance sheets; unnecessary tool invocation latency and failures on non-equity assets.
- **Empirical Evidence**:
  Verified in `tests/adversarial/test_m1_adversarial_challenge.py::test_crypto_graph_execution_fails_to_prune_fundamentals` and `test_crypto_debate_stale_fundamentals_injection`.
- **Recommended Mitigation**:
  1. In `TradingAgentsGraph.propagate()`, if `asset_type == "crypto"` (or ticker matches crypto bases), dynamically ensure `Fundamentals Analyst` is omitted from execution, or in `create_fundamentals_analyst`, immediately return an empty/absent report if `state.get("asset_type") == "crypto"`.
  2. In `bull_researcher.py` and `bear_researcher.py`, if `asset_type == "crypto"`, strictly suppress `{fundamentals_label}` and force `fundamentals_report = ""` so stale equity text cannot be injected.

---

### [High] Challenge 3: 21 Failing Tests in `core/tests/` Obscured by Selective Verification

- **Assumption Challenged**: All 275+ unit and integration tests pass cleanly with zero regressions.
- **Attack Scenario**:
  Running `python -m pytest "core/tests/"` reveals 21 failures:
  - 12 failures in `core/tests/test_i18n_coverage.py`: Line 15 still points to the old path `_AGENTS_DIR = Path(__file__).resolve().parents[1] / "tradingagents" / "agents"` instead of `core/agents`.
  - 2 failures in `core/tests/test_reporting.py` and `core/tests/test_sec_edgar.py`: Line 149 references `tradingagents.__version__` which raises `NameError`.
  - 1 failure in `core/tests/test_cli_commands.py`: `subprocess.run(["python", "-m", "cli.main"])` fails with `ModuleNotFoundError: No module named 'cli'`.
  - 3 failures in `core/tests/test_suite_isolation.py`.
  - 2 failures in `core/tests/test_cli_prefs.py`.
  - 1 failure in `core/tests/test_ticker_symbol_handling.py`.
- **Blast Radius**:
  Inability to run standard automated CI/CD pipelines across `core/`; broken subprocess invocations; broken internationalization regression coverage.
- **Empirical Evidence**:
  Direct execution of `python -m pytest "core/tests/" -q` exited with code 1: `21 failed, 1399 passed, 6 skipped in 36.48s`.
- **Recommended Mitigation**:
  Update `_AGENTS_DIR` in `core/tests/test_i18n_coverage.py` to point to `core/agents`; replace `tradingagents.__version__` with `core.__version__` in test assertions; ensure `cli` module is accessible in subshell test environments.

---

## Stress Test Results

Executed via `tests/adversarial/test_m1_adversarial_challenge.py` (9/9 passed):

| Scenario | Expected Behavior | Actual Behavior | Result | Finding |
|---|---|---|---|---|
| `test_trader_proposal_numerical_leakage_nan` | `TraderProposal` should coerce NaN to None | Leaks `float('nan')`, fails strict JSON | PASS (Reproduced Defect) | Critical Defect Confirmed |
| `test_trader_proposal_numerical_leakage_infinity` | `TraderProposal` should coerce Inf to None | Leaks `float('inf')` | PASS (Reproduced Defect) | Critical Defect Confirmed |
| `test_trader_proposal_string_range_coercion` | Coerces `"150-160"` to `None` | Coerces to `None` | PASS | Expected Behavior |
| `test_jev_adapter_nan_bypass_exploit` | Rejects NaN proposal | Bypasses stop check, approves NaN proposal | PASS (Reproduced Defect) | Safety Bypass Confirmed |
| `test_jev_adapter_stop_loss_rules` | Enforces buy/sell stop ordering on valid floats | Correctly approves/rejects valid floats | PASS | Expected Behavior |
| `test_jev_adapter_determinism_100_runs` | 100 identical runs for score & variants | 100% identical outputs | PASS | Verified Deterministic |
| `test_crypto_debate_stale_fundamentals_injection` | Suppresses stale equity text in crypto debate | Injects stale 10-K text into Bull & Bear prompts | PASS (Reproduced Defect) | Deliberation Leakage Confirmed |
| `test_crypto_graph_execution_fails_to_prune_fundamentals` | Omits Fundamentals Analyst in crypto mode | Executes Fundamentals Analyst on `BTC-USD` | PASS (Reproduced Defect) | Pruning Failure Confirmed |
| `test_reflection_memory_extreme_price_swings` | Handles +500% and -90% without tag corruption | Correctly formats tags and resolves past context | PASS | Settlement Math Robust |

---

## Unchallenged Areas

- Live on-chain execution with MetaMask (assigned to Milestone 2).
- Web frontend UI streaming and WebSocket telemetry (assigned to Milestone 3).
- Remote cloud execution (`agy --remote-agent`) (assigned to Milestone 4).
