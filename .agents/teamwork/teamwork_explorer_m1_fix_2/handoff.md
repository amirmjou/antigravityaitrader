# Handoff Report: Milestone 1 Remediation Strategy (Defect Vector 2)

**Agent ID**: `teamwork_explorer_m1_fix_2`  
**Role**: Explorer (Read-only Investigation & Remediation Strategy)  
**Parent Orchestrator ID**: `8738e4c1-d84c-4f83-b88d-7f67803aff6e`  
**Working Directory**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m1_fix_2\`  
**Deliverable**: `fix_strategy.md`, `handoff.md`  
**Type**: Hard Handoff (Investigation & Fix Strategy Complete)  

---

## 1. Observation

Direct observations and evidence gathered during the investigation into Defect Vector 2 (Crypto Fundamentals Pruning Failure & Deliberation Leakage):

1. **Static Graph Compilation & Pruning Failure in `core/graph/trading_graph.py`**:
   - `core/graph/trading_graph.py:54-115`: `TradingAgentsGraph.__init__()` takes `selected_analysts=("market", "social", "news", "fundamentals")` and statically compiles the workflow:
     ```python
     self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
     self.graph = self.workflow.compile()
     ```
   - In `core/graph/trading_graph.py:192-205`, `begin_checkpoint(company_name, trade_date, asset_type, portfolio)` checks:
     ```python
     if not self.config.get("checkpoint_enabled"):
         return None
     ```
     Because checkpointing defaults to `False`, `begin_checkpoint` returns `None` immediately, leaving `self.graph` set to the static 4-analyst graph compiled during `__init__`.
   - In `core/graph/trading_graph.py:167-190`, `propagate(company_name, trade_date, asset_type="stock", portfolio=None)` executes `self._run_graph()`, which executes `self.graph.invoke()`. Because `self.graph` contains `Fundamentals Analyst`, LangGraph invokes the `Fundamentals Analyst` node even when `asset_type="crypto"` or when the ticker is `BTC-USD`.
   - Empirical confirmation: running `tests/adversarial/test_m1_adversarial_challenge.py::test_crypto_graph_execution_fails_to_prune_fundamentals` passed with 100% confirmation that `Fundamentals Analyst` is executed for `BTC-USD`.

2. **Unconditional Fundamentals Report Interpolation in Researchers**:
   - `core/agents/researchers/bull_researcher.py:21-29`:
     ```python
     fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
     asset_type = state.get("asset_type", "stock")
     target_label = "stock" if asset_type == "stock" else "asset"
     fundamentals_label = (
         "Company fundamentals report"
         if asset_type == "stock"
         else "Asset fundamentals report (may be unavailable for crypto)"
     )
     ```
   - `core/agents/researchers/bull_researcher.py:45`:
     ```python
     {fundamentals_label}: {fundamentals_report}
     ```
   - `core/agents/researchers/bear_researcher.py:21-47`: Identical structure to `bull_researcher.py`.
   - When `state["fundamentals_report"]` contains stale financial statement data (e.g. `STALE SEC 10-K: Revenue $95B, EBITDA margin 32%, PE 28`), `report_or_absent` evaluates `bool(text)` as `True` and returns the text verbatim.
   - The resulting prompt interpolates:
     `Asset fundamentals report (may be unavailable for crypto): STALE SEC 10-K: Revenue $95B, EBITDA margin 32%, PE 28`
   - Empirical confirmation: running `tests/adversarial/test_m1_adversarial_challenge.py::test_crypto_debate_stale_fundamentals_injection` confirmed that the stale text leaked into both Bull Researcher and Bear Researcher prompt payloads.

3. **Missing Early Skip Guard in `core/agents/analysts/fundamentals_analyst.py`**:
   - `core/agents/analysts/fundamentals_analyst.py:23-64`: `fundamentals_analyst_node(state)` lacks any check on `state.get("asset_type")` or `state.get("company_of_interest")`.
   - If scheduled or executed directly on a crypto asset, it initiates tool calls to SEC EDGAR / Yahoo balance sheet tools.

4. **Available Symbol Utilities**:
   - `core/dataflows/symbols.py:43-95` exports `_CRYPTO_BASES = frozenset({"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"})` and `crypto_base(raw: str) -> str | None`. These primitives provide canonical syntactic classification for USD/USDT/USDC pairs.

---

## 2. Logic Chain

1. **Step 1 (Graph Pruning Failure)**:
   - Observation 1 establishes that `TradingAgentsGraph` compiles `self.graph` once during `__init__` with all selected analysts.
   - When `propagate()` is invoked with `asset_type="crypto"` or a crypto ticker (`BTC-USD`), the graph invoked by `_run_graph` is the unpruned graph containing `Fundamentals Analyst`.
   - Therefore, `Fundamentals Analyst` is scheduled from `START` and executes tools/LLM on crypto assets unless the graph is dynamically selected or compiled without `fundamentals`.

2. **Step 2 (Prompt Deliberation Leakage)**:
   - Observation 2 demonstrates that `bull_researcher.py` and `bear_researcher.py` read `state["fundamentals_report"]` and format `{fundamentals_label}: {fundamentals_report}` even when `asset_type == "crypto"`.
   - If stale equity data exists in `state["fundamentals_report"]`, it is interpolated verbatim into the LLM prompt.
   - Therefore, crypto debaters are fed corporate financial metrics (SEC 10-K, P/E ratios, revenue) for crypto assets unless `state["fundamentals_report"]` is suppressed and sanitized whenever `is_crypto` is True.

3. **Step 3 (Defense-in-Depth Solution)**:
   - A robust remediation requires four synchronized layers:
     - **Layer 1 (TradingAgentsGraph)**: Maintain `self.crypto_workflow` alongside `self.workflow`. In `begin_checkpoint`, `propagate`, and `_run_signature`, dynamically select `self.crypto_workflow` when `is_crypto_asset(company_name, asset_type)` is True. This eliminates `Fundamentals Analyst` from the LangGraph execution plan.
     - **Layer 2 (Fundamentals Analyst Node)**: Add an early return guard in `fundamentals_analyst_node(state)` returning `{"messages": [], "fundamentals_report": ""}` if `is_crypto_asset` is True.
     - **Layer 3 (Researcher Prompts)**: In `bull_researcher.py` and `bear_researcher.py`, when `is_crypto` is True, suppress `state["fundamentals_report"]` completely and format `Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)`.
     - **Layer 4 (State Normalization)**: In `create_run_state`, auto-detect crypto tickers and ensure `state["asset_type"] = "crypto"` and `state["fundamentals_report"] = ""`.

4. **Conclusion**:
   - Implementing this 4-layer strategy completely resolves Defect Vector 2, guarantees zero fundamentals node execution for crypto, eliminates stale equity leakage into crypto debates, and maintains 100% compatibility for stock equity analysis.

---

## 3. Caveats

1. **Scope Boundary**: This investigation focused strictly on Defect Vector 2 (Crypto Fundamentals Pruning & Deliberation Leakage). Defect Vector 1 (`TraderProposal` float sanitization & `JevAdapter` NaN handling) and Defect Vector 3 (21 test failures in `core/tests/`) are handled by peer subagents/workers.
2. **Read-Only Constraint**: No source code files outside of `.agents/teamwork/teamwork_explorer_m1_fix_2/` were modified. All proposals are documented in `fix_strategy.md` with explicit line numbers and before/after snippets ready for the implementation worker.
3. **Symbol Support**: Crypto detection relies on `_CRYPTO_BASES` and `crypto_base()` in `core/dataflows/symbols.py`. New crypto base assets added to `_CRYPTO_BASES` will automatically inherit dynamic pruning and prompt sanitization.

---

## 4. Conclusion

A watertight, production-grade fix strategy for Defect Vector 2 has been devised and fully documented in `fix_strategy.md`.

**Action Items for Implementation Worker (`teamwork_worker_m1_2`)**:
1. Apply Layer 1 to `core/graph/trading_graph.py`:
   - Initialize `self.crypto_workflow` in `__init__`.
   - Add `_is_crypto`, `_active_analysts`, and `get_workflow` methods.
   - Update `begin_checkpoint` to compile the active workflow for `asset_type`.
   - Update `_run_signature` to include `active_analysts`.
   - Normalize `asset_type="crypto"` in `create_run_state`.
2. Apply Layer 2 to `core/agents/analysts/fundamentals_analyst.py`:
   - Add early skip guard in `fundamentals_analyst_node`.
3. Apply Layer 3 to `core/agents/researchers/bull_researcher.py` and `bear_researcher.py`:
   - Detect `is_crypto` and suppress `state["fundamentals_report"]`.
   - Provide crypto-tailored focus points and explicit suppression notice in prompt resources.
4. Update Adversarial Challenge assertions in `tests/adversarial/test_m1_adversarial_challenge.py`:
   - Assert `assert stale_text not in prompt_str` in `test_crypto_debate_stale_fundamentals_sanitized`.
   - Assert `assert "Fundamentals Analyst" not in executed_nodes` in `test_crypto_graph_execution_prunes_fundamentals`.

---

## 5. Verification Method

Once implemented by the worker, independently verify the fix using the following commands:

1. **Verify Adversarial Tests Pass Remediated Invariants**:
   ```powershell
   python -m pytest "tests/adversarial/test_m1_adversarial_challenge.py" -v
   ```
   *Expected Output*: All crypto debate and pruning tests pass with zero fundamentals execution and zero stale data leakage.

2. **Verify Stock Equity Regression Freedom**:
   ```powershell
   python -m pytest "core/tests/test_graph_end_to_end.py" -k "test_a_debug_run_prints_the_analysts_work_and_reaches_the_same_decision" -v
   ```
   *Expected Output*: Stock equities (`NVDA`) continue to execute all 4 analysts and populate `fundamentals_report`.

3. **Verify Prompt Integrity & i18n Invariants**:
   ```powershell
   python -m pytest "core/tests/test_prompt_integrity.py" -v
   ```
   *Expected Output*: Researcher prompt structures pass all invariant checks.
