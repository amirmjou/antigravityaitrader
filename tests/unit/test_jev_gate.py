"""
Unit Test Suite for Jev Design Quality Gate Subsystem (Milestone 3 - Feature F18).
Tests DesignSummaryExtractor, UIQualityGateValidator, thresholds, and CLI runner.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from visualization.quality.jev_gate import (
    DEFAULT_INSTITUTIONAL_BRIEF,
    DesignSummaryExtractor,
    QualityGateVerdict,
    ScoreMetric,
    UIQualityGateValidator,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def validator():
    return UIQualityGateValidator()


@pytest.fixture
def valid_html():
    return """
    <!DOCTYPE html>
    <html class="theme-dark">
    <body>
        <main class="grid-3-col layout-asymmetric">
            <div id="agent-stream" class="debate-arena arena-card bull bear">
                Bull vs Bear
            </div>
            <div id="candlestick-chart">
                <canvas id="candleChart"></canvas>
            </div>
            <div id="order-book-depth">
                <div id="guardrail-shield">Shield</div>
                <button id="btn-confirm-swap">Confirm On-Chain Swap</button>
            </div>
        </main>
    </body>
    </html>
    """


@pytest.fixture
def valid_css():
    return """
    :root {
        --bg-base: #0b0e14;
        --bg-surface: #121820;
        --bull: #00c076;
        --bear: #ff4d4f;
        font-family: ui-monospace, monospace;
        font-variant-numeric: tabular-nums;
    }
    """


@pytest.fixture
def broken_html():
    return """
    <html>
    <body style="font-family: 'Comic Sans MS';">
        <div style="color: yellow; background: white;">
            broken layout unaligned text no buttons missing chart missing colors poor unhedged unreadable
        </div>
    </body>
    </html>
    """


# ===========================================================================
# 1. DesignSummaryExtractor Unit Tests
# ===========================================================================

class TestDesignSummaryExtractor:
    def test_extract_from_valid_text_structure(self, valid_html, valid_css):
        summary = DesignSummaryExtractor.extract_from_text(valid_html, valid_css)
        assert "3-column asymmetric" in summary
        assert "AI Debate Arena" in summary
        assert "HTML5 Canvas" in summary
        assert "L2 order book" in summary
        assert "6-layer" in summary
        assert "Alpine dark space slate" in summary
        assert "Contrast tokens" in summary
        assert "monospace tabular" in summary
        assert "Confirm On-Chain Swap" in summary
        assert "Complete, polished, robust" in summary

    def test_extract_from_broken_text_structure(self, broken_html):
        summary = DesignSummaryExtractor.extract_from_text(broken_html, "")
        assert "broken unaligned missing elements" in summary
        assert "No prominent execution button" in summary

    def test_extract_from_actual_templates(self):
        html_file = Path("visualization/web/templates/index.html")
        css_file = Path("visualization/web/static/css/dashboard.css")
        assert html_file.exists()
        assert css_file.exists()

        summary = DesignSummaryExtractor.extract_from_files(html_file, css_file)
        assert "3-column asymmetric" in summary
        assert "AI Debate Arena" in summary
        assert "Confirm On-Chain Swap" in summary
        assert "Contrast tokens" in summary

    def test_extract_detects_button_cta_label(self):
        html = '<button id="btn-execute">Execute Trade Order</button>'
        summary = DesignSummaryExtractor.extract_from_text(html)
        assert "Execute Trade Order" in summary


# ===========================================================================
# 2. UIQualityGateValidator Unit Tests
# ===========================================================================

class TestUIQualityGateValidator:
    def test_evaluate_valid_institutional_dashboard(self, validator, valid_html, valid_css):
        summary = DesignSummaryExtractor.extract_from_text(valid_html, valid_css)
        verdict: QualityGateVerdict = validator.evaluate_summary(
            brief=DEFAULT_INSTITUTIONAL_BRIEF,
            design_summary=summary,
            min_composite_score=3.0,
        )
        assert verdict.passed is True
        assert verdict.composite_score >= 3.0
        assert verdict.ready_to_ship is True
        assert verdict.brand_fit in ["Acceptable", "Good", "Excellent"]
        assert verdict.visual_quality in ["Acceptable", "Good", "Excellent"]
        assert verdict.clarity in ["Acceptable", "Good", "Excellent"]
        assert verdict.cta_strength in ["Acceptable", "Good", "Excellent"]
        assert len(verdict.rejection_reasons) == 0

    def test_evaluate_broken_ui_rejection(self, validator, broken_html):
        summary = DesignSummaryExtractor.extract_from_text(broken_html, "")
        verdict: QualityGateVerdict = validator.evaluate_summary(
            brief=DEFAULT_INSTITUTIONAL_BRIEF,
            design_summary=summary,
            min_composite_score=3.0,
        )
        assert verdict.passed is False
        assert len(verdict.rejection_reasons) > 0
        assert any("ready_to_ship" in r or "score" in r or "insufficient" in r for r in verdict.rejection_reasons)

    def test_strict_mode_threshold_evaluation(self, validator, valid_html, valid_css):
        summary = DesignSummaryExtractor.extract_from_text(valid_html, valid_css)
        verdict = validator.evaluate_summary(
            brief=DEFAULT_INSTITUTIONAL_BRIEF,
            design_summary=summary,
            min_composite_score=4.0,  # Strict mode requires >= 4.0
        )
        assert verdict.composite_score >= 4.0
        assert verdict.passed is True

    def test_custom_mock_adapter_injection(self):
        class MockJev:
            def review_design(self, brief, summary):
                return {
                    "brand_fit": {"type": "score", "score": "Weak", "confidence": 0.5},
                    "visual_quality": {"type": "score", "score": "Weak", "confidence": 0.5},
                    "clarity": {"type": "score", "score": "Weak", "confidence": 0.5},
                    "cta_strength": {"type": "score", "score": "Weak", "confidence": 0.5},
                    "ready_to_ship": {"type": "noul", "noul": False, "probability": 0.1, "confidence": 0.8},
                    "next_focus": {"type": "choice", "choice": "contrast", "confidence": 0.5},
                }

        v = UIQualityGateValidator(jev_client=MockJev())
        verdict = v.evaluate_summary("brief", "summary")
        assert verdict.passed is False
        assert verdict.ready_to_ship is False
        assert verdict.recommended_focus == "contrast"
        assert verdict.composite_score == 2.0  # 4 * Weak (2.0) / 4 = 2.0

    def test_verdict_model_serialization(self):
        verdict = QualityGateVerdict(
            passed=True,
            composite_score=4.5,
            brand_fit="Excellent",
            visual_quality="Good",
            clarity="Good",
            cta_strength="Excellent",
            ready_to_ship=True,
            confidence=0.92,
            recommended_focus=None,
            rejection_reasons=[],
        )
        d = verdict.model_dump()
        assert d["passed"] is True
        assert d["composite_score"] == 4.5
        assert d["ready_to_ship"] is True

    def test_score_metric_bounds(self):
        s = ScoreMetric(score="Good", confidence=0.88)
        assert s.score == "Good"
        assert s.confidence == 0.88
        assert "Poor" in s.legend
