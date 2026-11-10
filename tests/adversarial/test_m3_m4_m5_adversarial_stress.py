"""Adversarial Stress & Boundary Verification for Milestones 3, 4, and 5."""
from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from crypto_pipeline import (
    ATRSizingEngine,
    CCXTMarketFeed,
    CryptoDeliberationPipeline,
    JevCryptoDecisionScorer,
    RemoteAgentDeliberationBridge,
)
from simulation import MultiAssetBacktestGridRunner, PaperTradingEngine
from visualization.telemetry.hub import TelemetryHub


class TestMilestone3AdversarialFixes:
    def test_frontend_app_js_uses_real_metamask_eth_send_transaction(self):
        """Verify app.js calls window.ethereum.request({ method: 'eth_sendTransaction' }) and contains no fakeTxHash."""
        app_js_path = Path(__file__).resolve().parent.parent.parent / "visualization" / "web" / "static" / "js" / "app.js"
        content = app_js_path.read_text(encoding="utf-8")
        assert "eth_sendTransaction" in content
        assert "window.ethereum.request" in content
        assert "fakeTxHash" not in content

    def test_sse_backlog_replay_preserves_strict_chronological_order(self):
        """Verify subscribe_sse queues historical backlog before registering live subscriber."""
        async def _run():
            hub = TelemetryHub(max_event_backlog=100)
            ev1 = hub.publish_event("agent_thought", "Market Analyst", "Token 1")
            ev2 = hub.publish_event("agent_thought", "Bull Researcher", "Token 2")
            ev3 = hub.publish_event("agent_thought", "Bear Researcher", "Token 3")

            q = await hub.subscribe_sse(since_id=ev1.event_id)
            ev4 = hub.publish_event("decision", "Portfolio Manager", "Token 4")

            received_ids = []
            while not q.empty():
                item = await q.get()
                received_ids.append(item.event_id)

            assert received_ids == [ev2.event_id, ev3.event_id, ev4.event_id]
            await hub.unsubscribe_sse(q)

        asyncio.run(_run())


class TestMilestone4And5AdversarialStress:
    @pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf"), 0.0, -50.0])
    def test_atr_sizer_rejects_non_finite_and_non_positive_values(self, bad_val):
        sizer = ATRSizingEngine()
        with pytest.raises(ValueError):
            sizer.calculate_atr14_sizing("BTC/USDT", portfolio_value_usd=bad_val)

    @pytest.mark.parametrize("bad_val", [float("nan"), float("inf"), float("-inf")])
    def test_paper_trader_rejects_non_finite_floats(self, bad_val):
        engine = PaperTradingEngine(initial_cash_usd=10000.0)
        with pytest.raises(ValueError):
            engine.place_order("BTC/USDT", "Buy", bad_val, 88500.0)
        with pytest.raises(ValueError):
            engine.place_order("BTC/USDT", "Buy", 0.01, bad_val)

    def test_remote_agent_failure_modes_handled_strictly(self):
        for mode in ["timeout", "malformed_json", "crash"]:
            bridge = RemoteAgentDeliberationBridge(should_fail=True, failure_mode=mode)
            with pytest.raises(Exception):
                bridge.execute_and_parse("BTC")

    def test_jev_scorer_rejects_nan_drawdown(self):
        scorer = JevCryptoDecisionScorer()
        with pytest.raises(ValueError):
            scorer.evaluate_trade_risk("BTC-USD", current_drawdown=float("nan"))
