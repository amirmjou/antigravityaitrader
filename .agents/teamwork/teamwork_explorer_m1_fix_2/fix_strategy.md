# Fix Strategy: Defect Vector 2 (Crypto Fundamentals Pruning & Deliberation Leakage)

**Agent ID**: `teamwork_explorer_m1_fix_2`  
**Milestone**: Milestone 1 Remediation (Iteration 2)  
**Parent Orchestrator ID**: `8738e4c1-d84c-4f83-b88d-7f67803aff6e`  
**Status**: COMPLETE (Read-Only Proposal)  

---

## 1. Executive Summary

During the Milestone 1 Adversarial Challenge (Challenger 2), Defect Vector 2 exposed two interrelated architectural vulnerabilities in the multi-agent deliberation framework:
1. **Graph-Level Pruning Failure**: `TradingAgentsGraph` statically compiles `self.workflow` with all 4 analyst nodes (`market`, `social`, `news`, `fundamentals`) upon instantiation. Calling `graph.propagate("BTC-USD", "2026-04-18", asset_type="crypto")` invokes this static graph without pruning the `Fundamentals Analyst` node, causing corporate SEC filings tools to run on cryptocurrency tickers.
2. **Debate Deliberation Leakage**: `Bull Researcher` (`core/agents/researchers/bull_researcher.py`) and `Bear Researcher` (`bear_researcher.py`) unconditionally interpolate `state["fundamentals_report"]` into their prompt templates. If stale equity data exists in the state, it leaks verbatim into the crypto debate, leading LLM agents to evaluate corporate 10-K balance sheets, P/E ratios, and revenues for decentralized cryptocurrency assets like Bitcoin or Ethereum.

This document outlines a 4-layer, defense-in-depth remediation strategy that guarantees zero fundamentals execution for crypto assets and zero corporate data leakage into deliberations, while maintaining 100% backward compatibility for stock equities.

---

## 2. Root Cause Analysis

### 2.1 Static Workflow Compilation in `TradingAgentsGraph`
- **Location**: `core/graph/trading_graph.py:54-115`, `183-255`
- **Mechanism**:
  - `TradingAgentsGraph.__init__()` takes `selected_analysts=("market", "social", "news", "fundamentals")` and immediately builds `self.workflow = self.graph_setup.setup_graph(...)` and `self.graph = self.workflow.compile()`.
  - When `propagate()` is called, `self.checkpoint_scope` calls `begin_checkpoint(company_name, trade_date, asset_type, portfolio)`.
  - If `checkpoint_enabled` is `False` (the default in production and testing), `begin_checkpoint` returns `None` immediately, leaving `self.graph` set to the static 4-analyst graph compiled during `__init__`.
  - If `checkpoint_enabled` is `True`, `begin_checkpoint` compiles `self.workflow.compile(checkpointer=saver)`, which still references the static 4-analyst workflow.
  - In both paths, `Fundamentals Analyst` is scheduled as a parallel entry node from `START` alongside `Market Analyst`, `Sentiment Analyst`, and `News Analyst`.

### 2.2 Unconditional String Interpolation in Bull & Bear Prompts
- **Location**: `core/agents/researchers/bull_researcher.py:21-47`, `core/agents/researchers/bear_researcher.py:21-49`
- **Mechanism**:
  - Both researchers extract `fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")`.
  - Even though they check `asset_type = state.get("asset_type", "stock")` to change the section label to `"Asset fundamentals report (may be unavailable for crypto)"`, they format `{fundamentals_label}: {fundamentals_report}` unconditionally.
  - If `state["fundamentals_report"]` contains prior equity text (e.g. from state reuse, cross-asset memory, or test fixtures), `report_or_absent` treats it as a valid report and passes it through verbatim into `{fundamentals_report}`.
  - Furthermore, prompt focus guidelines instruct debaters to focus on "financial health", "revenue projections", and "P/E ratios", prompting hallucinated corporate comparisons.

### 2.3 Lack of Crypto Guard inside `Fundamentals Analyst` Node
- **Location**: `core/agents/analysts/fundamentals_analyst.py:23-64`
- **Mechanism**:
  - `fundamentals_analyst_node(state)` does not check `state.get("asset_type")` or inspect whether `state["company_of_interest"]` is a cryptocurrency.
  - If invoked directly or through an unpruned graph, it proceeds directly to `take_turn` and LLM invocation with SEC EDGAR / Yahoo financial statement tools.

---

## 3. Comprehensive Remediation Strategy

The remediation is structured across four layers:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: TradingAgentsGraph Dynamic Workflow Selection      │
│  - Pre-build self.crypto_workflow without 'fundamentals'    │
│  - Select crypto workflow in begin_checkpoint / propagate   │
│  - Key active analysts into checkpoint signature            │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│ Layer 2: Fundamentals Analyst Node Skip Guard (Defense)    │
│  - If asset_type == 'crypto' or ticker in _CRYPTO_BASES:   │
│    Immediately return {"messages": [], "report": ""}        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│ Layer 3: Deliberation Prompt Sanitization (Bull & Bear)     │
│  - If is_crypto: suppress state["fundamentals_report"]      │
│  - Inject explicit crypto notice; zero corporate data leak │
│  - Adapt debate focus points for crypto protocol dynamics   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────┐
│ Layer 4: State Normalization & Symbol Detection             │
│  - Auto-coerce asset_type="crypto" if ticker is crypto base │
│  - Clear initial state fundamentals_report for crypto runs  │
└─────────────────────────────────────────────────────────────┘
```

### Shared Asset Classifier Utility
To ensure uniform classification across `trading_graph.py`, `fundamentals_analyst.py`, `bull_researcher.py`, and `bear_researcher.py`, use the canonical symbol utilities already in `core/dataflows/symbols.py`:

```python
from core.dataflows.symbols import _CRYPTO_BASES, crypto_base

def is_crypto_asset(ticker: str | None = None, asset_type: str | None = None) -> bool:
    """Classify whether the given ticker/asset_type represents a cryptocurrency.
    
    Returns True if:
    1. asset_type == "crypto"
    2. ticker (or clean base) is in _CRYPTO_BASES (e.g. BTC, ETH, SOL, AVAX)
    3. crypto_base(ticker) is in _CRYPTO_BASES (e.g. BTC-USD, ETH-USDT, SOLUSD)
    """
    if asset_type and str(asset_type).strip().lower() == "crypto":
        return True
    if ticker and isinstance(ticker, str):
        clean = ticker.strip().upper()
        if clean in _CRYPTO_BASES:
            return True
        base = crypto_base(clean)
        if base is not None and base in _CRYPTO_BASES:
            return True
    return False
```

---

## 4. Detailed Specification of Code Changes

### Change 1: `core/graph/trading_graph.py`

#### A. In `__init__` (lines 108-115)
Pre-build both the standard workflow and the crypto-pruned workflow:
```python
<<<< BEFORE
        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False
====
        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the standard workflow:
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        
        # Set up the crypto-pruned workflow (fundamentals dynamically omitted):
        crypto_analysts = tuple(a for a in selected_analysts if a != "fundamentals")
        if crypto_analysts != self.selected_analysts:
            self.crypto_workflow = self.graph_setup.setup_graph(crypto_analysts, memory_node=self._memory_step)
        else:
            self.crypto_workflow = self.workflow

        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False
>>>>
```

#### B. Helper methods in `TradingAgentsGraph`:
Add workflow accessor and analyst resolution methods:
```python
    def _is_crypto(self, asset_type: str = "stock", company_name: str | None = None) -> bool:
        from core.dataflows.symbols import _CRYPTO_BASES, crypto_base
        if asset_type and str(asset_type).strip().lower() == "crypto":
            return True
        if company_name and isinstance(company_name, str):
            clean = company_name.strip().upper()
            if clean in _CRYPTO_BASES or (crypto_base(clean) and crypto_base(clean) in _CRYPTO_BASES):
                return True
        return False

    def _active_analysts(self, asset_type: str = "stock", company_name: str | None = None) -> tuple[str, ...]:
        if self._is_crypto(asset_type, company_name):
            return tuple(a for a in self.selected_analysts if a != "fundamentals")
        return self.selected_analysts

    def get_workflow(self, asset_type: str = "stock", company_name: str | None = None):
        """Return the workflow tailored to the asset class (crypto prunes fundamentals)."""
        if self._is_crypto(asset_type, company_name):
            return self.crypto_workflow
        return self.workflow
```

#### C. In `_run_signature` (lines 140-165)
Incorporate the active analysts into the checkpoint signature so that crypto runs have independent checkpoints:
```python
<<<< BEFORE
        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
====
        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        active_analysts = self._active_analysts(asset_type, company_name)
        return "|".join([
            "analysts=" + ",".join(active_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
>>>>
```

#### D. In `begin_checkpoint` and `end_checkpoint` (lines 192-238)
Ensure `self.graph` compiles the active workflow (whether checkpointing is enabled or disabled):
```python
<<<< BEFORE
    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        self._resuming = False
        if not self.config.get("checkpoint_enabled"):
            return None
        signature = self._run_signature(asset_type, portfolio)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)
====
    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        self._resuming = False
        workflow = self.get_workflow(asset_type, company_name)
        if not self.config.get("checkpoint_enabled"):
            self.graph = workflow.compile()
            return None
        signature = self._run_signature(asset_type, portfolio, company_name=company_name)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = workflow.compile(checkpointer=saver)
>>>>
```
And in `end_checkpoint`:
```python
<<<< BEFORE
    def end_checkpoint(self):
        """Restore the plain uncheckpointed graph after a checkpointed run."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()
        self._resuming = False
====
    def end_checkpoint(self):
        """Restore the plain uncheckpointed graph after a checkpointed run."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
        self.graph = self.workflow.compile()
        self._resuming = False
>>>>
```

#### E. In `create_run_state` (lines 293-307)
Normalize crypto asset types automatically:
```python
<<<< BEFORE
    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        trade_date = _validate_trade_date(trade_date)
        return self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
            portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
        )
====
    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        trade_date = _validate_trade_date(trade_date)
        if self._is_crypto(asset_type, company_name):
            asset_type = "crypto"
        return self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
            portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
        )
>>>>
```

---

### Change 2: `core/agents/analysts/fundamentals_analyst.py`

Add an immediate skip guard at the top of `fundamentals_analyst_node`:
```python
<<<< BEFORE
def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
====
def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        from core.dataflows.symbols import _CRYPTO_BASES, crypto_base
        asset_type = state.get("asset_type", "stock")
        company_name = state.get("company_of_interest", "")
        clean = company_name.strip().upper() if isinstance(company_name, str) else ""
        is_crypto = (
            asset_type == "crypto"
            or clean in _CRYPTO_BASES
            or (crypto_base(clean) is not None and crypto_base(clean) in _CRYPTO_BASES)
        )
        if is_crypto:
            logger.info("Skipping Fundamentals Analyst for crypto asset '%s'", company_name)
            return {
                "messages": [],
                "fundamentals_report": "",
            }

        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
>>>>
```

---

### Change 3: `core/agents/researchers/bull_researcher.py`

Sanitize prompt formatting and suppress `fundamentals_report` for crypto:
```python
<<<< BEFORE
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()
====
        from core.dataflows.symbols import _CRYPTO_BASES, crypto_base
        company_name = state.get("company_of_interest", "")
        clean = company_name.strip().upper() if isinstance(company_name, str) else ""
        asset_type = state.get("asset_type", "stock")
        is_crypto = (
            asset_type == "crypto"
            or clean in _CRYPTO_BASES
            or (crypto_base(clean) is not None and crypto_base(clean) in _CRYPTO_BASES)
        )
        target_label = "asset" if is_crypto else "stock"

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")

        if is_crypto:
            fundamentals_section = "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)."
            focus_points = """Key points to focus on:
- Growth Potential: Highlight network adoption, protocol utility, ecosystem growth, and liquidity dynamics.
- Competitive Advantages: Emphasize decentralization, security, developer activity, and tokenomics.
- Positive Indicators: Use market structure, on-chain sentiment, technical trends, and recent news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data."""
        else:
            fundamentals_report = report_or_absent(state.get("fundamentals_report", ""), "fundamentals")
            fundamentals_section = f"Company fundamentals report: {fundamentals_report}"
            focus_points = """Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data."""

        instrument_context = get_instrument_context_from_state(state)

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

{focus_points}

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_section}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()
>>>>
```

---

### Change 4: `core/agents/researchers/bear_researcher.py`

Apply the symmetric sanitization in `bear_researcher.py`:
```python
<<<< BEFORE
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()
====
        from core.dataflows.symbols import _CRYPTO_BASES, crypto_base
        company_name = state.get("company_of_interest", "")
        clean = company_name.strip().upper() if isinstance(company_name, str) else ""
        asset_type = state.get("asset_type", "stock")
        is_crypto = (
            asset_type == "crypto"
            or clean in _CRYPTO_BASES
            or (crypto_base(clean) is not None and crypto_base(clean) in _CRYPTO_BASES)
        )
        target_label = "asset" if is_crypto else "stock"

        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")

        if is_crypto:
            fundamentals_section = "Asset fundamentals: Not applicable for cryptocurrency assets (corporate financial statements suppressed)."
            focus_points = """Key points to focus on:
- Risks and Challenges: Highlight network vulnerabilities, regulatory headwinds, liquidity risks, or macroeconomic volatility.
- Competitive Weaknesses: Emphasize vulnerabilities such as competing protocols, declining active addresses, or security risks.
- Negative Indicators: Use adverse news, whale outflows, technical breakdown levels, or sentiment deterioration to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts."""
        else:
            fundamentals_report = report_or_absent(state.get("fundamentals_report", ""), "fundamentals")
            fundamentals_section = f"Company fundamentals report: {fundamentals_report}"
            focus_points = """Key points to focus on:
- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts."""

        instrument_context = get_instrument_context_from_state(state)

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

{focus_points}

Resources available:

{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_section}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()
>>>>
```

---

## 5. Verification & Test Harness Plan

### 5.1 Adversarial Challenge Invariant Tests
In `tests/adversarial/test_m1_adversarial_challenge.py`, the challenger wrote two tests demonstrating the defect:
1. `test_crypto_debate_stale_fundamentals_injection`
2. `test_crypto_graph_execution_fails_to_prune_fundamentals`

After the implementation of the fix strategy:
1. **Debate Stale Fundamentals Sanitization Assertion**:
   ```python
   def test_crypto_debate_stale_fundamentals_sanitized():
       stale_text = "STALE SEC 10-K: Revenue $95B, EBITDA margin 32%, PE 28"
       ...
       bull_node(state)
       prompt_str = str(captured_prompts[0])
       assert stale_text not in prompt_str, "Stale financial data must NEVER leak into Bull prompt"
       assert "Asset fundamentals: Not applicable" in prompt_str

       captured_prompts.clear()
       bear_node(state)
       prompt_str_bear = str(captured_prompts[0])
       assert stale_text not in prompt_str_bear, "Stale financial data must NEVER leak into Bear prompt"
       assert "Asset fundamentals: Not applicable" in prompt_str_bear
   ```

2. **Graph Dynamic Pruning Assertion**:
   ```python
   def test_crypto_graph_execution_prunes_fundamentals(monkeypatch):
       ...
       graph = TradingAgentsGraph(config=cfg)
       # Full workflow retains all analysts for stock runs
       assert "Fundamentals Analyst" in graph.workflow.nodes

       # Propagating for crypto dynamically prunes Fundamentals Analyst
       graph.propagate("BTC-USD", "2026-04-18", asset_type="crypto")
       assert "Fundamentals Analyst" not in executed_nodes, (
           "Fundamentals Analyst must NOT execute for crypto assets"
       )
   ```

### 5.2 Preservation of Existing Test Invariants
- `test_i18n_coverage.py`: Confirmed that `get_language_instruction()` is preserved at the end of both `bull_researcher.py` and `bear_researcher.py` prompts.
- `test_prompt_integrity.py`: Confirmed that `report_or_absent` continues to say "not available" for unselected stock reports.
- `test_graph_end_to_end.py`: Stock runs (`NVDA`, `AAPL`) continue to execute all 4 analysts and write `fundamentals.md`.
