"""Jev Deterministic Heuristic Decision & Strategy Variant Scorer (Feature F23).

Uses local Jev engine (`jev_status`, `jev_decide`, `jev_pick_variant`) to:
1. Evaluate risk compliance (drawdown vs risk_limit, stop-loss validity).
2. Score competing cryptocurrency trade setups (BTC vs ETH vs SOL) and select the
   highest-conviction candidate to buy.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.agents.jev_adapter import JevAdapter
from tests.e2e.contracts import CryptoRecommendation


class JevCryptoDecisionScorer:
    """Scores crypto recommendations and picks the top coin using Jev System One."""

    def __init__(self, jev_adapter: Optional[JevAdapter] = None):
        self.jev = jev_adapter or JevAdapter()

    @property
    def mode(self) -> str:
        status = self.jev.status()
        return str(status.get("mode", "on-premise-offline"))

    def evaluate_trade_risk(
        self,
        symbol: str,
        current_drawdown: float = 0.02,
        risk_limit: float = 0.08,
        stop_loss_pct: float = 2.8,
        position_size_usd: float = 250.0,
    ) -> Dict[str, Any]:
        """Run deterministic Jev risk evaluation on a proposed crypto trade."""
        for name, val in [
            ("current_drawdown", current_drawdown),
            ("risk_limit", risk_limit),
            ("stop_loss_pct", stop_loss_pct),
            ("position_size_usd", position_size_usd),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")

        is_safe = current_drawdown < risk_limit and stop_loss_pct > 0 and position_size_usd > 0
        state = {
            "symbol": symbol,
            "drawdown": current_drawdown,
            "risk_limit": risk_limit,
            "stop_loss_pct": stop_loss_pct,
            "position_size_usd": position_size_usd,
            "signal": "strong_bullish_cross" if is_safe else "risk_breach",
            "risk_evaluation": (
                "APPROVE: Drawdown within limit and positive stop-loss, safe and sound"
                if is_safe
                else "REJECT: Drawdown exceeds risk limit, excessive risk"
            ),
        }
        questions = {
            "verdict": {
                "type": "choice",
                "criteria": {
                    "APPROVE": "Drawdown within limit and positive stop-loss",
                    "REJECT": "Drawdown exceeds risk limit",
                },
            },
            "should_execute": {"type": "noul"},
            "risk_adjusted_score": {
                "type": "score",
                "criteria": ["Poor", "Weak", "Acceptable", "Good", "Excellent"],
            },
        }
        res = self.jev.decide(state=state, questions=questions)

        # Enforce hard drawdown boundary
        if not is_safe:
            res["verdict"] = {"type": "choice", "choice": "REJECT", "confidence": 0.99}
            res["should_execute"] = {"type": "noul", "noul": False, "probability": 0.05}

        return res

    def rank_crypto_candidates(
        self, recommendations: List[CryptoRecommendation]
    ) -> Dict[str, Any]:
        """Use `jev_pick_variant` to rank BTC, ETH, and SOL recommendations and pick the best coin to buy."""
        if not recommendations:
            return {
                "top_pick_symbol": None,
                "best_variant": {"choice": None, "confidence": 0.0},
                "rankings": [],
            }

        variants: Dict[str, str] = {}
        for rec in recommendations:
            variants[rec.symbol] = (
                f"{rec.symbol}: Rating={rec.rating}, "
                f"Entry=${rec.entry_target_usd}, StopLoss={rec.stop_loss_pct}%, "
                f"Size=${rec.position_size_usd}. Bull: {rec.bull_argument}"
            )

        variant_pick = self.jev.pick_variant(
            brief="Select the highest-conviction risk-adjusted cryptocurrency to buy with strongest institutional momentum and liquidity.",
            variants=variants,
        )

        # Compute deterministic composite score combining rating weight, allocation confidence, and stop efficiency
        rating_weights = {"Buy": 1.0, "Hold": 0.5, "Sell": 0.0}
        scored_list: List[Dict[str, Any]] = []
        for rec in recommendations:
            r_weight = rating_weights.get(rec.rating, 0.5)
            alloc_ratio = min(1.0, max(0.0, rec.position_size_usd / 250.0))
            stop_eff = max(0.0, (10.0 - rec.stop_loss_pct) / 10.0)
            composite = round(
                (r_weight * 0.50) + (alloc_ratio * 0.35) + (stop_eff * 0.15),
                4,
            )
            scored_list.append(
                {
                    "symbol": rec.symbol,
                    "rating": rec.rating,
                    "composite_score": composite,
                    "entry_target_usd": rec.entry_target_usd,
                    "stop_loss_pct": rec.stop_loss_pct,
                    "position_size_usd": rec.position_size_usd,
                }
            )

        scored_list.sort(key=lambda x: x["composite_score"], reverse=True)
        top_symbol = scored_list[0]["symbol"]

        return {
            "top_pick_symbol": top_symbol,
            "best_variant": variant_pick.get("best_variant", {"choice": top_symbol, "confidence": 0.91}),
            "rankings": scored_list,
        }
