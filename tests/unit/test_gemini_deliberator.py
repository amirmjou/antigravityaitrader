"""
Unit tests for GeminiDeliberator consensus engine.
"""
import json
from unittest.mock import MagicMock, patch
from core.ai.gemini_deliberator import GeminiDeliberator


def test_gemini_deliberator_heuristic_fallback():
    deliberator = GeminiDeliberator(api_key="")
    assert not deliberator.is_configured

    # Test strong bullish momentum
    result = deliberator.deliberate(
        candidate_action="BUY WETH",
        spot_px=3135.0,
        short_ma=3140.0,
        long_ma=3120.0,
        rsi=58.0,
        holdings_desc="0.00035 ETH, $1.00 USDC",
    )
    assert "approved" in result
    assert result["approved"] is True
    assert result["action"] == "BUY WETH"
    assert result["confidence_pct"] >= 65.0
    assert result["source"] == "heuristic_fallback"


def test_gemini_deliberator_choppy_market_veto():
    deliberator = GeminiDeliberator(api_key="")
    # Test very weak spread (sideways chop)
    result = deliberator.deliberate(
        candidate_action="BUY WETH",
        spot_px=3120.0,
        short_ma=3120.10,
        long_ma=3120.00,
        rsi=50.0,
        holdings_desc="0.00035 ETH, $1.00 USDC",
    )
    # Weak spread should be vetoed by consensus heuristic
    assert result["approved"] is False
    assert result["action"] == "HOLD"


def test_gemini_format_market_intelligence():
    deliberator = GeminiDeliberator(api_key="")
    report = deliberator.format_market_intelligence(
        spot_px=3130.0,
        short_ma=3135.0,
        long_ma=3125.0,
        rsi=55.0,
        holdings_desc="0.00035 ETH, $1.00 USDC",
    )
    assert "GEMINI AI COGNITIVE MARKET ANALYSIS" in report
    assert "ETH Spot Price:" in report
    assert "AI Confidence:" in report


def test_gemini_live_api_mock():
    deliberator = GeminiDeliberator(api_key="AIzaSyMockKeyForTestingOnly1234567890")
    assert deliberator.is_configured

    mock_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "approved": True,
                                "action": "BUY",
                                "confidence_pct": 87.5,
                                "regime": "BULLISH_EXPANSION",
                                "risk_level": "LOW",
                                "rationale": "Strong momentum breakout confirmed by volume."
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_gemini_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = deliberator.deliberate(
            candidate_action="BUY WETH",
            spot_px=3150.0,
            short_ma=3160.0,
            long_ma=3140.0,
            rsi=62.0,
            holdings_desc="0.00035 ETH, $1.00 USDC",
        )
        assert res["approved"] is True
        assert res["confidence_pct"] == 87.5
        assert res["source"] == "gemini_1.5_flash"
