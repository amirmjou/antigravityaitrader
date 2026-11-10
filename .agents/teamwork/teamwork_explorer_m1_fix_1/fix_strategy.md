# Defect Vector 1 Remediation Strategy: Float Sanitization, RFC 8259 Compliance, & Jev Safety Resilience

**Author**: `teamwork_explorer_m1_fix_1`  
**Role**: Explorer / Investigator  
**Date**: 2026-11-06  
**Target Files**:
- `core/agents/schemas.py`
- `core/agents/jev_adapter.py`
- `tests/adversarial/test_m1_adversarial_challenge.py`
- `tests/adversarial/test_m1_adversarial_stress.py`

---

## 1. Executive Summary

Milestone 1 Iteration 1 revealed critical numerical and safety vulnerabilities in `core/agents/schemas.py` and `core/agents/jev_adapter.py`:
1. `_coerce_optional_float()` in `schemas.py` fails to sanitize non-finite floats (`float('nan')`, `float('inf')`, `float('-inf')`) and string equivalents (`"nan"`, `"Infinity"`, `"-Infinity"`), leaking `NaN` into `TraderProposal` and `PortfolioDecision`. This crashes strict RFC 8259 JSON serialization (`json.dumps(p.model_dump(), allow_nan=False)`) and corrupts downstream token allocation calculations in M2 execution guardrails.
2. Direct attribute assignment (e.g. `p.entry_price = float('nan')`) bypasses Pydantic validation because `validate_assignment=True` and `allow_inf_nan=False` were omitted from model configurations.
3. In `JevAdapter.score_trader_proposal()`, the IEEE 754 property where `float('nan') > 0 == False` causes `has_entry` to evaluate to `False`. As a result, the stop-loss validity check is skipped, `stop_valid` defaults to `True`, and an invalid order proposal with `entry_price=NaN` is approved for live execution.
4. In `JevAdapter.pick_variant()`, passing an empty criteria dictionary or sequence crashes with an unhandled `ValueError: max() arg is an empty sequence`.

This strategy provides an exact, watertight remediation design following a defense-in-depth model across schema validation, model configuration, and heuristic engine boundaries.

---

## 2. Root Cause & Defect Analysis

### 2.1 Defect 1.1: `_coerce_optional_float` Non-Finite Leakage
- **Location**: `core/agents/schemas.py:33-58`
- **Observed Mechanism**:
  ```python
  if not isinstance(value, str):
      return value  # Leaks float('nan'), float('inf'), bool (True/False)
  ...
  try:
      return float(cleaned)  # Python float('nan') and float('Infinity') succeed!
  except ValueError:
      return None
  ```
  `float("nan")` and `float("Infinity")` do NOT raise `ValueError` in Python; they parse directly into IEEE 754 special values. Because `_NULLISH_FLOAT` lacks `"nan"` and `"infinity"` tokens, string representations parse into `NaN`/`Inf`.
- **Downstream Consequence**:
  - `TraderProposal(entry_price=float('nan'))` retains `nan`.
  - `json.dumps(p.model_dump(), allow_nan=False)` raises `ValueError: Out of range float values are not JSON compliant`.
  - In M2 execution guardrails, calculating order quantity (`allocation / entry_price`) produces `NaN`, throwing errors during token amount integer conversion (`int(NaN)` raises `ValueError`).

### 2.2 Defect 1.2: Missing Model Configuration & Post-Validation in Schemas
- **Location**: `core/agents/schemas.py:146-194` (`TraderProposal`), `225-270` (`PortfolioDecision`)
- **Observed Mechanism**:
  `TraderProposal` and `PortfolioDecision` lack `ConfigDict(allow_inf_nan=False, validate_assignment=True)` (unlike `Position` in `core/portfolio.py:26`). Consequently:
  - If a float bypasses preprocessing, Pydantic's core validator accepts `NaN` and `Inf` as valid `float` instances.
  - Later mutation (`p.entry_price = float('nan')`) bypasses all validators.

### 2.3 Defect 1.3: IEEE 754 Comparison Bypass in `JevAdapter.score_trader_proposal`
- **Location**: `core/agents/jev_adapter.py:237-248`
- **Observed Mechanism**:
  ```python
  has_stop = stop_loss is not None and stop_loss > 0
  has_entry = entry_price is not None and entry_price > 0
  ...
  stop_valid = True
  if is_buy and has_entry and has_stop:
      stop_valid = stop_loss < entry_price
  elif is_sell and has_entry and has_stop:
      stop_valid = stop_loss > entry_price
  ```
  When `entry_price = float('nan')`:
  - `float('nan') > 0` evaluates to `False`.
  - `has_entry` becomes `False`.
  - The `if is_buy and has_entry and has_stop:` condition evaluates to `False`.
  - `stop_valid` remains `True`!
  - `eval_result.get("risk_acceptable", {}).get("noul", False)` evaluates to `True` for typical trade rationales.
  - `approved` becomes `True`!
  An order with `NaN` entry price is approved by the safety gate.
  Furthermore, if `proposal` is a raw dictionary or has missing entry price with a stop loss (`has_stop and not has_entry`), stop loss validity cannot be established, yet `stop_valid` defaulted to `True`.

### 2.4 Defect 1.4: `evaluate_choice` and `pick_variant` Empty Sequence Crash
- **Location**: `core/agents/jev_adapter.py:61-83`
- **Observed Mechanism**:
  ```python
  for key, desc in criteria.items():
      ...
  exp_scores = {k: math.exp(v * 3.0) for k, v in scores.items()}
  total_exp = sum(exp_scores.values()) or 1.0
  probs = {k: round(v / total_exp, 3) for k, v in exp_scores.items()}
  best_key = max(probs, key=probs.get)  # CRASH: max() arg is an empty sequence
  ```
  If `criteria` is empty `{}` or `[]`, `probs` is `{}`. Calling `max({})` raises `ValueError: max() arg is an empty sequence`.
  Additionally, passing a list of variant strings crashes because `criteria.items()` assumes a dictionary.

---

## 3. Comprehensive Fix Specifications

### 3.1 Target 1: `core/agents/schemas.py`

#### A. Expand `_NULLISH_FLOAT` (Lines 30-31)
```python
_NULLISH_FLOAT = {
    "", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown",
    "nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity",
}
```

#### B. Harden `_coerce_optional_float(value)` (Lines 33-59)
```python
import math
from typing import Any

def _coerce_optional_float(value: Any) -> float | None:
    """Normalise an LLM-written optional numeric field before validation.

    Coerces placeholder strings ("None", "N/A"), percentages ("15%"),
    formatted currencies ("$1,234.50"), non-numeric strings, booleans, and
    non-finite float values (NaN, +Inf, -Inf, 'nan', 'Infinity') to None
    or a valid finite float. Ensures prices are strictly finite and non-negative.
    """
    if value is None:
        return None
    # In Python, bool is a subclass of int (isinstance(True, int) is True).
    # Explicitly reject boolean values.
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if text.lower() in _NULLISH_FLOAT or text.endswith("%"):
        return None

    cleaned = text.replace(",", "").lstrip("$€£¥").strip()
    try:
        val = float(cleaned)
        if not math.isfinite(val):
            return None
        return val
    except (ValueError, TypeError):
        return None
```

#### C. Update `TraderProposal` Schema (Lines 146-194)
Add `ConfigDict(allow_inf_nan=False, validate_assignment=True)`, `_nullish_float_to_none` (mode="before"), and `_validate_finite_positive` (mode="after"):
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader."""

    model_config = ConfigDict(allow_inf_nan=False, validate_assignment=True)

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: float | None = Field(
        default=None,
        description=(
            "Optional entry price target as an absolute number in the instrument's "
            "quote currency (e.g. 189.5), never a percentage or a range. Omit it "
            "if you cannot state a specific level."
        ),
    )
    stop_loss: float | None = Field(
        default=None,
        description=(
            "Optional stop-loss as an absolute price in the instrument's quote "
            "currency (e.g. 172.0), never a percentage. Convert a percentage "
            "distance to the price level it implies, or omit it."
        ),
    )
    position_sizing: str | None = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )
    symbol: str = Field(
        default="",
        description="The ticker/symbol of the asset (e.g. BTC-USD, ETH-USD, AAPL).",
    )

    @field_validator("entry_price", "stop_loss", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)

    @field_validator("entry_price", "stop_loss", mode="after")
    @classmethod
    def _validate_finite_positive(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not math.isfinite(v) or v <= 0:
            return None
        return v
```

#### D. Update `PortfolioDecision` Schema (Lines 225-270)
```python
class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager."""

    model_config = ConfigDict(allow_inf_nan=False, validate_assignment=True)

    rating: PortfolioRating = Field(...)
    executive_summary: str = Field(...)
    investment_thesis: str = Field(...)
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: str | None = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )

    @field_validator("price_target", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)

    @field_validator("price_target", mode="after")
    @classmethod
    def _validate_finite_positive(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not math.isfinite(v) or v <= 0:
            return None
        return v
```

#### E. Update `SentimentReport` Schema (Lines 315-368)
Add `model_config = ConfigDict(allow_inf_nan=False, validate_assignment=True)` to prevent any mutation to NaN or Infinity.

---

### 3.2 Target 2: `core/agents/jev_adapter.py`

#### A. Harden `evaluate_choice()` against Empty or Malformed Criteria (Lines 61-83)
```python
def evaluate_choice(
    state_str: str,
    instructions: str,
    criteria: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    """Evaluate choices and return the winning candidate with probability distribution.

    Gracefully handles empty criteria, non-dict iterables, and empty probability sets
    without raising sequence errors.
    """
    if not criteria:
        return {
            "type": "choice",
            "choice": None,
            "confidence": 0.0,
            "probabilities": {},
        }

    # Normalize sequence of strings/items to dictionary format
    if isinstance(criteria, (list, tuple, set)):
        criteria = {str(item): item for item in criteria}
    elif not isinstance(criteria, dict):
        return {
            "type": "choice",
            "choice": None,
            "confidence": 0.0,
            "probabilities": {},
            "error": f"Invalid criteria type: {type(criteria).__name__}",
        }

    if not criteria:
        return {
            "type": "choice",
            "choice": None,
            "confidence": 0.0,
            "probabilities": {},
        }

    scores = {}
    combined_context = f"{instructions}\n{state_str}"

    for key, desc in criteria.items():
        desc_str = json.dumps(desc) if isinstance(desc, (dict, list)) else str(desc)
        base_sim = _semantic_overlap(f"{key} {desc_str}", combined_context)
        scores[key] = max(0.1, base_sim)

    # Softmax normalization
    exp_scores = {k: math.exp(v * 3.0) for k, v in scores.items()}
    total_exp = sum(exp_scores.values()) or 1.0
    probs = {k: round(v / total_exp, 3) for k, v in exp_scores.items()}

    best_key = max(probs, key=probs.get) if probs else None
    return {
        "type": "choice",
        "choice": best_key,
        "confidence": probs[best_key] if best_key is not None else 0.0,
        "probabilities": probs,
    }
```

#### B. Update `pick_variant()` Guard (Lines 164-180)
```python
    def pick_variant(self, brief: str, variants: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        """Evaluate multiple strategy or design variants and pick the best candidate.

        Corresponds to the MCP tool `jev_pick_variant`.
        """
        if not variants:
            return {
                "best_variant": {
                    "type": "choice",
                    "choice": None,
                    "confidence": 0.0,
                    "probabilities": {},
                }
            }
        questions = {
            "best_variant": {
                "type": "choice",
                "instructions": (
                    f"Given brief '{brief}', evaluate which variant best balances risk, reward, "
                    "downside protection, and execution viability."
                ),
                "criteria": variants,
            }
        }
        return run_local_jev({"brief": brief}, questions)
```

#### C. Harden `score_trader_proposal()` Safety Boundary (Lines 215-286)
```python
    def score_trader_proposal(
        self,
        proposal: TraderProposal | dict[str, Any],
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministically score a TraderProposal against risk criteria before execution.

        Enforces:
        1. Action validity (Buy, Hold, Sell)
        2. Strict numerical finiteness of entry_price and stop_loss (rejects NaN, Inf, strings)
        3. Mandatory stop-loss presence and directionality (Buy: stop < entry, Sell: stop > entry)
        4. Invalidation when stop-loss is provided without a valid entry price
        """
        prop_data = proposal.model_dump() if isinstance(proposal, TraderProposal) else dict(proposal)
        action = prop_data.get("action", "")
        if hasattr(action, "value"):
            action = action.value
        entry_price = prop_data.get("entry_price")
        stop_loss = prop_data.get("stop_loss")
        position_sizing = prop_data.get("position_sizing") or ""

        # Numerical validation: strictly reject non-finite (NaN, Inf) or invalid types
        if entry_price is not None:
            if not isinstance(entry_price, (int, float)) or not math.isfinite(entry_price) or entry_price <= 0:
                return {
                    "approved": False,
                    "action": action,
                    "stop_valid": False,
                    "heuristics": {},
                    "score": "Poor",
                    "confidence": 1.0,
                    "rejection_reason": f"Invalid or non-finite entry_price: {entry_price}",
                }

        if stop_loss is not None:
            if not isinstance(stop_loss, (int, float)) or not math.isfinite(stop_loss) or stop_loss <= 0:
                return {
                    "approved": False,
                    "action": action,
                    "stop_valid": False,
                    "heuristics": {},
                    "score": "Poor",
                    "confidence": 1.0,
                    "rejection_reason": f"Invalid or non-finite stop_loss: {stop_loss}",
                }

        has_stop = stop_loss is not None and stop_loss > 0
        has_entry = entry_price is not None and entry_price > 0
        is_buy = action.lower() == "buy"
        is_sell = action.lower() == "sell"

        stop_valid = True
        if is_buy or is_sell:
            if has_stop and not has_entry:
                # A stop loss cannot be verified without a known entry price
                stop_valid = False
            elif is_buy and has_entry and has_stop:
                stop_valid = stop_loss < entry_price
            elif is_sell and has_entry and has_stop:
                stop_valid = stop_loss > entry_price

        state_payload = {
            "action": action,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "position_sizing": position_sizing,
            "stop_valid": stop_valid,
            "market_context": market_context or {},
        }

        questions = {
            "risk_acceptable": {
                "type": "noul",
                "instructions": "Is the proposed trade order structure sound with safe stop-loss protection?",
            },
            "order_quality": {
                "type": "score",
                "instructions": "Quality of entry, stop-loss, and position sizing specification",
                "criteria": ["Poor", "Weak", "Acceptable", "Good", "Excellent"],
            },
        }

        eval_result = run_local_jev(state_payload, questions)

        approved = (
            action in ("Buy", "Hold", "Sell")
            and stop_valid
            and eval_result.get("risk_acceptable", {}).get("noul", False)
        )

        return {
            "approved": approved,
            "action": action,
            "stop_valid": stop_valid,
            "heuristics": eval_result,
            "score": eval_result.get("order_quality", {}).get("score", "Acceptable"),
            "confidence": eval_result.get("risk_acceptable", {}).get("confidence", 0.8),
        }
```

---

## 4. Test Suite Harmonization & Updates

Once the fixes are applied by the implementation worker, the following test updates must be made:

### 4.1 Update `tests/adversarial/test_m1_adversarial_challenge.py`
In Iteration 1, the challenger wrote tests asserting that vulnerabilities existed. In Iteration 2, those assertions must be inverted to assert the secured behavior:

1. **`test_trader_proposal_numerical_leakage_nan()`**:
   ```python
   def test_trader_proposal_numerical_leakage_nan():
       p_float_nan = TraderProposal(
           action=TraderAction.BUY,
           reasoning="Test proposal",
           entry_price=float("nan"),
           stop_loss=100.0,
           symbol="BTC-USD",
       )
       # Fixed: NaN coerced to None, avoiding numerical leakage
       assert p_float_nan.entry_price is None

       p_str_nan = TraderProposal(
           action=TraderAction.BUY,
           reasoning="Test proposal",
           entry_price="nan",
           stop_loss=100.0,
           symbol="BTC-USD",
       )
       assert p_str_nan.entry_price is None

       # Strict RFC 8259 JSON serialization now succeeds!
       dumped = json.dumps(p_float_nan.model_dump(), allow_nan=False)
       assert '"entry_price": null' in dumped
   ```

2. **`test_trader_proposal_numerical_leakage_infinity()`**:
   ```python
   def test_trader_proposal_numerical_leakage_infinity():
       p_inf = TraderProposal(
           action=TraderAction.BUY,
           reasoning="Test proposal",
           entry_price=float("inf"),
           stop_loss=100.0,
           symbol="ETH-USD",
       )
       assert p_inf.entry_price is None

       p_str_inf = TraderProposal(
           action=TraderAction.BUY,
           reasoning="Test proposal",
           entry_price="Infinity",
           stop_loss=100.0,
           symbol="ETH-USD",
       )
       assert p_str_inf.entry_price is None
   ```

3. **`test_jev_adapter_nan_bypass_exploit()`**:
   ```python
   def test_jev_adapter_nan_bypass_exploit():
       jev = JevAdapter()
       # Case A: Dict with raw NaN
       score_raw = jev.score_trader_proposal({
           "action": "Buy",
           "reasoning": "Exploit proposal",
           "entry_price": float("nan"),
           "stop_loss": 50.0,
           "symbol": "BTC-USD",
       })
       assert score_raw["stop_valid"] is False
       assert score_raw["approved"] is False

       # Case B: Proposal with sanitized entry_price (None) and stop_loss (50.0)
       p_nan = TraderProposal(
           action=TraderAction.BUY,
           reasoning="Exploit proposal",
           entry_price=float("nan"),
           stop_loss=50.0,
           symbol="BTC-USD",
       )
       score_p = jev.score_trader_proposal(p_nan)
       assert score_p["stop_valid"] is False
       assert score_p["approved"] is False
   ```

### 4.2 Update `tests/adversarial/test_m1_adversarial_stress.py`
Update `test_pick_variant_with_empty_variants_raises_value_error` and `test_pick_variant_with_empty_list_raises_value_error` (lines 386-397) to assert the clean, non-crashing response:
```python
    def test_pick_variant_with_empty_variants_handled_gracefully(self):
        adapter = JevAdapter()
        res = adapter.pick_variant("Evaluation Brief", {})
        assert res["best_variant"]["choice"] is None
        assert res["best_variant"]["confidence"] == 0.0

    def test_pick_variant_with_empty_list_handled_gracefully(self):
        adapter = JevAdapter()
        res = adapter.pick_variant("Evaluation Brief", [])
        assert res["best_variant"]["choice"] is None
        assert res["best_variant"]["confidence"] == 0.0
```

---

## 5. Verification Commands & Acceptance Matrix

| Verification Target | Command | Expected Outcome |
|---------------------|---------|------------------|
| Adversarial Suite | `python -m pytest "tests/adversarial/test_m1_adversarial_challenge.py" -v` | All 9 tests PASS with inverted security assertions |
| Stress Suite | `python -m pytest "tests/adversarial/test_m1_adversarial_stress.py" -v` | All Jev edge case tests PASS |
| Core Jev & Antigravity Suite | `python -m pytest "core/tests/test_jev_adapter_and_antigravity.py" -v` | All 13 tests PASS |
| Core Structured Agents Suite | `python -m pytest "core/tests/test_structured_agents.py" -v` | All 42 tests PASS |
| Tier 1 E2E Multi-Agent Tests | `python -m pytest "tests/e2e/test_tier1_f01_f07_multi_agent.py" -v` | All 25 tests PASS |
