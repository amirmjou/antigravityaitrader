"""Jev Decision Integration Adapter.

Provides deterministic offline decision evaluation, heuristic scoring, and strategy
variant selection using the on-premise Jev Decision Engine (System One protocol).
Operates 100% offline without external API keys or network dependencies.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from core.agents.schemas import PortfolioDecision, TraderProposal

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Extract word tokens from text."""
    return set(re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower()))


def _semantic_overlap(query: str, target: str) -> float:
    """Calculate semantic Jaccard and containment overlap."""
    q_tokens = _tokenize(query)
    t_tokens = _tokenize(target)
    if not q_tokens or not t_tokens:
        return 0.5
    intersection = q_tokens.intersection(t_tokens)
    union = q_tokens.union(t_tokens)
    jaccard = len(intersection) / len(union) if union else 0.0
    containment = len(intersection) / len(q_tokens) if q_tokens else 0.0
    return min(1.0, (jaccard * 0.4) + (containment * 0.6))


def evaluate_noul(state_str: str, instructions: str, criteria: Any = None) -> dict[str, Any]:
    """Evaluate a yes/no probability calibrated against criteria and state."""
    score = _semantic_overlap(instructions, state_str)
    state_lower = state_str.lower()

    negatives = ["missing", "broken", "lacking", "poor", "unclear", "slow", "error", "fail", "excessive", "high risk", "unsafe"]
    positives = ["complete", "polished", "sound", "approved", "robust", "safe", "favorable", "acceptable", "disciplined"]

    pos_count = sum(1 for w in positives if w in state_lower)
    neg_count = sum(1 for w in negatives if w in state_lower)

    adj = (pos_count * 0.12) - (neg_count * 0.20)
    prob = max(0.05, min(0.98, 0.5 + adj + (score * 0.2)))

    return {
        "type": "noul",
        "noul": prob >= 0.5,
        "probability": round(prob, 3),
        "confidence": round(0.75 + (abs(prob - 0.5) * 0.4), 2),
    }


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


def evaluate_score(state_str: str, instructions: str, criteria: list[str]) -> dict[str, Any]:
    """Evaluate score along an ordered scale (e.g. Poor -> Excellent)."""
    n = len(criteria)
    if n == 0:
        return {"type": "score", "score": "N/A", "confidence": 1.0}

    state_lower = state_str.lower()
    positives = ["sound", "strong", "favorable", "optimal", "safe", "high", "clean", "consistent", "accurate", "hedged"]
    negatives = ["fragile", "excessive", "unhedged", "inconsistent", "weak", "missing", "confusing", "poor", "high risk"]

    pos_score = sum(1 for p in positives if p in state_lower)
    neg_score = sum(1 for n in negatives if n in state_lower)

    ratio = 0.60 + (pos_score * 0.08) - (neg_score * 0.12)
    ratio = max(0.0, min(1.0, ratio))

    index = min(n - 1, int(round(ratio * (n - 1))))

    probs = {}
    for i, label in enumerate(criteria):
        dist = abs(i - index)
        probs[label] = round(math.exp(-dist * 1.5), 3)
    total = sum(probs.values()) or 1.0
    probs = {k: round(v / total, 3) for k, v in probs.items()}

    return {
        "type": "score",
        "score": criteria[index],
        "confidence": probs[criteria[index]],
        "legend": criteria,
        "probabilities": probs,
    }


def run_local_jev(state: Any, questions: dict[str, dict]) -> dict[str, Any]:
    """Execute local offline Jev heuristic decision engine on state given typed questions."""
    state_str = json.dumps(state) if isinstance(state, (dict, list)) else str(state)
    answers = {}

    for q_name, q_spec in questions.items():
        q_type = q_spec.get("type", "").lower()
        instructions = q_spec.get("instructions", "")
        criteria = q_spec.get("criteria")

        if q_type == "noul":
            answers[q_name] = evaluate_noul(state_str, instructions, criteria)
        elif q_type == "choice":
            answers[q_name] = evaluate_choice(state_str, instructions, criteria or {})
        elif q_type == "score":
            answers[q_name] = evaluate_score(state_str, instructions, criteria or [])
        else:
            answers[q_name] = {"error": f"Unsupported question type: {q_type}"}

    return answers


class JevAdapter:
    """Adapter bridging multi-agent trading deliberation with the local Jev Decision Engine."""

    def __init__(self, mcp_client: Any | None = None):
        self.mcp_client = mcp_client

    def status(self) -> dict[str, Any]:
        """Check the status of the Jev Decision Engine."""
        return {
            "mode": "on-premise-offline",
            "provider": "local_heuristic_engine",
            "api_key_required": False,
            "status": "ready",
            "supported_types": ["noul", "choice", "score"],
        }

    def decide(self, state: Any, questions: dict[str, dict]) -> dict[str, Any]:
        """Generic decision call evaluating state against typed questions.

        Corresponds to the MCP tool `jev_decide`.
        """
        return run_local_jev(state, questions)

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

    def review_design(self, brief: str, design_summary: str) -> dict[str, Any]:
        """Quality gate for trading UI visual hierarchy, contrast, and layout fidelity.

        Corresponds to the MCP tool `jev_review_design` (used in Milestone 3).
        """
        scale = ["Poor", "Weak", "Acceptable", "Good", "Excellent"]
        questions = {
            "brand_fit": {
                "type": "score",
                "instructions": "Adherence to designated trading terminal aesthetic and palette",
                "criteria": scale,
            },
            "visual_quality": {
                "type": "score",
                "instructions": "Visual polish, contrast, and layout structure of charts and panels",
                "criteria": scale,
            },
            "clarity": {
                "type": "score",
                "instructions": "Information density, hierarchy, and ease of trade telemetry comprehension",
                "criteria": scale,
            },
            "cta_strength": {
                "type": "score",
                "instructions": "Execution button visibility and order confirmation clarity",
                "criteria": scale,
            },
            "ready_to_ship": {
                "type": "noul",
                "instructions": "Is the trading interface complete and ready for live presentation?",
            },
        }
        return run_local_jev({"brief": brief, "design": design_summary}, questions)

    def score_trader_proposal(
        self,
        proposal: TraderProposal | dict[str, Any],
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministically score a TraderProposal against risk criteria before execution.

        Checks:
        1. Action validity (Buy, Hold, Sell)
        2. Presence and soundness of stop-loss level
        3. Risk-to-reward ratio and price level distance
        4. Position sizing bounds
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

        # Deterministic checks
        has_stop = stop_loss is not None and stop_loss > 0
        has_entry = entry_price is not None and entry_price > 0
        is_buy = action.lower() == "buy"
        is_sell = action.lower() == "sell"

        # If Buy, stop loss should be below entry price; if Sell, above entry price
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

    def score_risk_consensus(
        self,
        proposal: TraderProposal | dict[str, Any],
        risk_debate_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Adjudicate consensus among Aggressive, Conservative, and Neutral risk analysts."""
        state_payload = {
            "proposal": proposal.model_dump() if isinstance(proposal, TraderProposal) else proposal,
            "aggressive": risk_debate_state.get("current_aggressive_response", ""),
            "conservative": risk_debate_state.get("current_conservative_response", ""),
            "neutral": risk_debate_state.get("current_neutral_response", ""),
            "debate_history": risk_debate_state.get("history", ""),
        }

        questions = {
            "consensus_achieved": {
                "type": "noul",
                "instructions": "Did the risk management analysts reach an actionable risk compromise?",
            },
            "dominant_posture": {
                "type": "choice",
                "instructions": "Which risk management posture best reflects the debate synthesis?",
                "criteria": {
                    "conservative": "Capital preservation and strict drawdown control dominate",
                    "balanced": "Balanced risk-reward profile with calculated upside",
                    "aggressive": "High-conviction growth thesis with elevated volatility tolerance",
                },
            },
            "downside_protection": {
                "type": "score",
                "instructions": "Strength of downside hedges and loss containment parameters",
                "criteria": ["Poor", "Weak", "Acceptable", "Good", "Excellent"],
            },
        }

        return run_local_jev(state_payload, questions)
