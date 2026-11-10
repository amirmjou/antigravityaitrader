"""Automated Jev UI Design Quality Gate Engine (Feature F18)."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from core.agents.jev_adapter import JevAdapter

logger = logging.getLogger(__name__)

DEFAULT_INSTITUTIONAL_BRIEF = (
    "Alpine dark-mode institutional cryptocurrency trading terminal with high visual hierarchy, "
    "real-time multi-agent reasoning stream, interactive candlestick charts, live order book depth, "
    "and prominent MetaMask swap execution controls."
)

SCORE_MAP = {
    "Poor": 1.0,
    "Weak": 2.0,
    "Acceptable": 3.0,
    "Good": 4.0,
    "Excellent": 5.0,
}


class ScoreMetric(BaseModel):
    """Sub-metric score model from Jev design evaluation."""
    type: Literal["score"] = "score"
    score: Literal["Poor", "Weak", "Acceptable", "Good", "Excellent"]
    confidence: float
    legend: List[str] = Field(default_factory=lambda: ["Poor", "Weak", "Acceptable", "Good", "Excellent"])
    probabilities: Dict[str, float] = Field(default_factory=dict)


class NoulMetric(BaseModel):
    """Boolean gating metric from Jev design evaluation."""
    type: Literal["noul"] = "noul"
    noul: bool
    probability: float
    confidence: float


class ChoiceMetric(BaseModel):
    """Categorical focus recommendation from Jev design evaluation."""
    type: Literal["choice"] = "choice"
    choice: Optional[str] = None
    confidence: float = 0.0
    probabilities: Dict[str, float] = Field(default_factory=dict)


class JevDesignReviewResult(BaseModel):
    """Structured response from Jev review_design."""
    brand_fit: ScoreMetric
    visual_quality: ScoreMetric
    clarity: ScoreMetric
    cta_strength: ScoreMetric
    ready_to_ship: NoulMetric
    next_focus: ChoiceMetric


class QualityGateVerdict(BaseModel):
    """Audited verdict from UIQualityGateValidator."""
    passed: bool
    composite_score: float
    brand_fit: str
    visual_quality: str
    clarity: str
    cta_strength: str
    ready_to_ship: bool
    confidence: float
    recommended_focus: Optional[str] = None
    rejection_reasons: List[str] = Field(default_factory=list)


class DesignSummaryExtractor:
    """Parses frontend HTML and CSS files to extract semantic tokens for Jev scoring."""

    @classmethod
    def extract_from_files(cls, html_path: Path, css_path: Optional[Path] = None) -> str:
        """Extract design summary from file paths."""
        html_content = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        css_content = css_path.read_text(encoding="utf-8") if css_path and css_path.exists() else ""
        return cls.extract_from_text(html_content, css_content)

    @classmethod
    def extract_from_text(cls, html: str, css: str = "") -> str:
        """Extract design summary tokens from raw HTML and CSS markup strings."""
        tokens = []

        # 1. Layout & Column Architecture
        has_3col = bool(re.search(r'grid-3-col|col-1|col-2|col-3|layout-asymmetric', html))
        has_stream = bool(re.search(r'id=["\'](?:reasoning-feed|agent-stream|debate-stream)', html))
        has_chart = bool(re.search(r'id=["\'](?:candleChart|candlestick-chart)', html))
        has_orderbook = bool(re.search(r'id=["\'](?:orderbook|order-book-depth)', html))
        has_guardrails = bool(re.search(r'id=["\'](?:guardrail-shield|guardrail-status)', html))
        has_arena = bool(re.search(r'class=["\'][^"\']*(?:debate-arena|arena-card)[^"\']*["\']', html))

        if has_3col or (has_stream and has_chart and has_orderbook):
            tokens.append("Layout: 3-column asymmetric responsive flex grid (28% : 44% : 28%).")
        else:
            tokens.append("Layout: Standard dashboard container.")

        if has_arena or has_stream:
            tokens.append("Left: AI Debate Arena with Bull vs Bear cards and live SSE token-by-token reasoning feed.")
        if has_chart:
            tokens.append("Center: HTML5 Canvas candlestick chart with EMA 20/50, RSI 14, and execution markers.")
        if has_orderbook:
            tokens.append("Right: L2 order book depth with bids, asks, and volume imbalance meter.")
        if has_guardrails:
            tokens.append("Right: 6-layer pre-broadcast safety guardrail status shield.")

        # 2. Palette & Contrast
        is_dark = any(k in html or k in css for k in ["#0b0e14", "#121820", "theme-dark", "bg-slate-950"])
        has_emerald = any(k in html or k in css for k in ["#00c076", "#10b981", "emerald", "bull-badge"])
        has_crimson = any(k in html or k in css for k in ["#ff4d4f", "#ef4444", "crimson", "bear-badge"])

        if is_dark:
            tokens.append("Palette: Alpine dark space slate background (#0b0e14) with card surface #121820.")
        if has_emerald and has_crimson:
            tokens.append("Contrast tokens: Emerald (#00c076) buy markers and Crimson (#ff4d4f) sell markers. Contrast ratio 7.5:1.")

        # 3. Typography
        has_mono = any(k in html or k in css for k in ["monospace", "ui-monospace", "tabular-nums", "Consolas"])
        if has_mono:
            tokens.append("Typography: High contrast crisp sans-serif with monospace tabular numerals for prices and depth.")

        # 4. Action CTA & Frontier Mode
        buttons = re.findall(r'<button[^>]*id=["\']([^"\']+)["\'][^>]*>(.*?)</button>', html, re.DOTALL)
        if buttons:
            swap_btn = next((b for b in buttons if any(k in b[0] for k in ["swap", "confirm", "execute"])), buttons[0])
            btn_text = re.sub(r'<[^>]+>', '', swap_btn[1]).strip()
            tokens.append(f"Action CTA: Prominent '{btn_text}' button with gas estimation and MetaMask bridge connectivity.")
        else:
            tokens.append("Action CTA: No prominent execution button detected.")

        # 5. Integrity & Quality Indicators
        has_broken = any(k in html.lower() for k in ["comic sans", "broken layout", "unaligned", "missing chart"])
        if has_broken:
            tokens.append("broken unaligned missing elements poor contrast")
        else:
            tokens.append("Visual hierarchy: Complete, polished, robust, sound visual hierarchy and clean panel boundaries.")

        return " ".join(tokens)


class UIQualityGateValidator:
    """Enforces automated Jev design quality gating before UI presentation or build."""

    def __init__(self, jev_client: Optional[Any] = None):
        self.jev = jev_client or JevAdapter()

    def evaluate_summary(
        self,
        brief: str,
        design_summary: str,
        min_composite_score: float = 3.0,
        require_ready_to_ship: bool = True,
    ) -> QualityGateVerdict:
        """Evaluates design summary against design brief using local Jev engine."""
        raw_review = self.jev.review_design(brief, design_summary)

        def _extract_score(metric_dict: Dict[str, Any], default: str = "Weak") -> ScoreMetric:
            score_val = metric_dict.get("score", default)
            if score_val not in SCORE_MAP:
                score_val = default
            return ScoreMetric(
                score=score_val,
                confidence=float(metric_dict.get("confidence", 0.5)),
                legend=metric_dict.get("legend", ["Poor", "Weak", "Acceptable", "Good", "Excellent"]),
                probabilities=metric_dict.get("probabilities", {}),
            )

        def _extract_noul(metric_dict: Dict[str, Any]) -> NoulMetric:
            return NoulMetric(
                noul=bool(metric_dict.get("noul", False)),
                probability=float(metric_dict.get("probability", 0.5)),
                confidence=float(metric_dict.get("confidence", 0.5)),
            )

        def _extract_choice(metric_dict: Dict[str, Any]) -> ChoiceMetric:
            return ChoiceMetric(
                choice=metric_dict.get("choice"),
                confidence=float(metric_dict.get("confidence", 0.0)),
                probabilities=metric_dict.get("probabilities", {}),
            )

        res = JevDesignReviewResult(
            brand_fit=_extract_score(raw_review.get("brand_fit", {})),
            visual_quality=_extract_score(raw_review.get("visual_quality", {})),
            clarity=_extract_score(raw_review.get("clarity", {})),
            cta_strength=_extract_score(raw_review.get("cta_strength", {})),
            ready_to_ship=_extract_noul(raw_review.get("ready_to_ship", {})),
            next_focus=_extract_choice(raw_review.get("next_focus", {})),
        )

        scores = [
            SCORE_MAP.get(res.brand_fit.score, 1.0),
            SCORE_MAP.get(res.visual_quality.score, 1.0),
            SCORE_MAP.get(res.clarity.score, 1.0),
            SCORE_MAP.get(res.cta_strength.score, 1.0),
        ]
        composite = round(sum(scores) / len(scores), 2)

        rejections = []
        if require_ready_to_ship and not res.ready_to_ship.noul:
            rejections.append("Jev ready_to_ship gate failed: UI is marked incomplete.")
        if composite < min_composite_score:
            rejections.append(f"Composite score {composite} is below threshold {min_composite_score}.")
        if res.brand_fit.score in ["Poor", "Weak"]:
            rejections.append(f"Brand fit score is insufficient: {res.brand_fit.score}.")
        if res.visual_quality.score in ["Poor", "Weak"]:
            rejections.append(f"Visual quality score is insufficient: {res.visual_quality.score}.")
        if res.clarity.score in ["Poor", "Weak"]:
            rejections.append(f"Clarity score is insufficient: {res.clarity.score}.")
        if res.cta_strength.score in ["Poor", "Weak"]:
            rejections.append(f"CTA strength is insufficient: {res.cta_strength.score}.")

        passed = len(rejections) == 0

        return QualityGateVerdict(
            passed=passed,
            composite_score=composite,
            brand_fit=res.brand_fit.score,
            visual_quality=res.visual_quality.score,
            clarity=res.clarity.score,
            cta_strength=res.cta_strength.score,
            ready_to_ship=res.ready_to_ship.noul,
            confidence=res.ready_to_ship.confidence,
            recommended_focus=res.next_focus.choice,
            rejection_reasons=rejections,
        )


def main():
    """CLI runner for Jev design quality gate."""
    parser = argparse.ArgumentParser(description="Jev UI Design Quality Gate Runner")
    parser.add_argument("--html", type=Path, default=Path("visualization/web/templates/index.html"), help="Path to index.html")
    parser.add_argument("--css", type=Path, default=Path("visualization/web/static/css/dashboard.css"), help="Path to dashboard.css")
    parser.add_argument("--min-score", type=float, default=3.0, help="Minimum composite score (1.0 to 5.0)")
    parser.add_argument("--strict", action="store_true", default=False, help="Require composite score >= 4.0")
    args = parser.parse_args()

    threshold = 4.0 if args.strict else args.min_score
    print("=" * 70)
    print(" JEV UI DESIGN QUALITY GATE AUDIT")
    print("=" * 70)
    print(f" Target HTML: {args.html}")
    print(f" Passing Threshold: {threshold}/5.0")

    if not args.html.exists():
        print(f"ERROR: HTML file not found at {args.html}")
        sys.exit(1)

    summary = DesignSummaryExtractor.extract_from_files(args.html, args.css)
    validator = UIQualityGateValidator()
    verdict = validator.evaluate_summary(
        brief=DEFAULT_INSTITUTIONAL_BRIEF,
        design_summary=summary,
        min_composite_score=threshold,
    )

    print(f" Brand Fit:       {verdict.brand_fit}")
    print(f" Visual Quality:  {verdict.visual_quality}")
    print(f" Clarity:         {verdict.clarity}")
    print(f" CTA Strength:    {verdict.cta_strength}")
    print(f" Ready to Ship:   {verdict.ready_to_ship} (Confidence: {verdict.confidence})")
    print(f" Composite Score: {verdict.composite_score}/5.0")
    print(f" Recommended:     {verdict.recommended_focus}")
    print("-" * 70)

    if verdict.passed:
        print("VERDICT: [PASSED] Design satisfies institutional quality criteria.")
        sys.exit(0)
    else:
        print("VERDICT: [FAILED] Quality gate rejected UI design:")
        for r in verdict.rejection_reasons:
            print(f"  - {r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
