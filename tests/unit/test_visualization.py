"""
Unit Test Suite for Visualization Subsystem (Milestone 3 - Features F15–F17).
Covers TelemetryHub ring buffer, SSE streaming, WebSocket telemetry manager,
ReasoningStreamCallbackHandler, and FastAPI application endpoints.
"""
from __future__ import annotations

import asyncio
import json
import time
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from visualization.server.app import create_visualization_app, DEFAULT_PORT
from visualization.server.connection_manager import TelemetryConnectionManager
from visualization.server.models import (
    AgentDeliberationEvent,
    ChartCandle,
    ExecutionMarker,
    GuardrailStateSnapshot,
    OrderBookSnapshot,
    TechnicalIndicators,
    UIStreamMessage,
)
from visualization.telemetry.callbacks import ReasoningStreamCallbackHandler
from visualization.telemetry.hub import TelemetryHub


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def hub():
    return TelemetryHub(max_event_backlog=100)


@pytest.fixture
def ws_manager():
    return TelemetryConnectionManager()


@pytest.fixture
def app(hub, ws_manager):
    return create_visualization_app(hub=hub, ws_manager=ws_manager)


@pytest.fixture
def client(app):
    return TestClient(app)


# ===========================================================================
# 1. TelemetryHub & Ring Buffer Unit Tests
# ===========================================================================

class TestTelemetryHub:
    def test_hub_initialization(self, hub):
        assert hub.max_event_backlog == 100
        assert len(hub.event_backlog) == 0
        assert hub.event_sequence == 0
        assert len(hub.event_stream) == 0

    def test_publish_event_monotonic_sequence(self, hub):
        ev1 = hub.publish_event("agent_thought", "Bull Researcher", "Thesis A")
        ev2 = hub.publish_event("debate_turn", "Bear Researcher", "Antithesis B")
        assert ev1.event_id == 1
        assert ev2.event_id == 2
        assert len(hub.event_stream) == 2
        assert hub.event_stream[-1].token == "Antithesis B"

    def test_ring_buffer_capacity_truncation(self):
        small_hub = TelemetryHub(max_event_backlog=5)
        for i in range(10):
            small_hub.publish_event("agent_thought", "Market Analyst", f"Token {i}")
        assert len(small_hub.event_stream) == 5
        assert small_hub.event_stream[0].token == "Token 5"
        assert small_hub.event_stream[-1].token == "Token 9"
        assert small_hub.event_sequence == 10

    def test_event_schema_serialization(self, hub):
        ev = hub.publish_event(
            "tool_call",
            "Market Analyst",
            "fetch_ticker(BTC/USDT)",
            snapshot={"price": 88500.0, "volume": 1200.0},
            agent_name="Analyst-1",
            debate_round=2,
            consensus_status="in_progress",
        )
        sse_str = ev.to_sse_frame()
        assert sse_str.startswith("id: 1\n")
        assert "event: tool_call\n" in sse_str
        assert "data: {" in sse_str
        assert "88500.0" in sse_str

    def test_candle_update_and_caching(self, hub):
        c = hub.update_candle({
            "timestamp_ms": 1730900000000,
            "open": 88000.0,
            "high": 89000.0,
            "low": 87800.0,
            "close": 88500.0,
            "volume": 1500.0,
        })
        assert isinstance(c, ChartCandle)
        assert hub.latest_candle.close == 88500.0

    def test_orderbook_imbalance_and_spread_calculation(self, hub):
        ob = hub.update_orderbook({
            "symbol": "BTC/USDT",
            "timestamp_ms": 1730900000000,
            "bids": [[88500.0, 15.0], [88490.0, 5.0]],
            "asks": [[88510.0, 3.0], [88520.0, 2.0]],
        })
        assert isinstance(ob, OrderBookSnapshot)
        assert ob.spread == 10.0
        # bids vol = 20.0, asks vol = 5.0 -> imbalance = 15/25 = 0.60
        assert round(ob.depth_imbalance, 2) == 0.60

    def test_indicators_update_and_caching(self, hub):
        ind = hub.update_indicators({
            "symbol": "BTC/USDT",
            "ema_20": 87500.0,
            "macd": 120.0,
            "rsi_14": 58.5,
            "atr_14": 1100.0,
        })
        assert isinstance(ind, TechnicalIndicators)
        assert hub.latest_indicators.rsi_14 == 58.5

    def test_execution_marker_recording_bounded(self, hub):
        for i in range(60):
            hub.record_execution({
                "type": "EXECUTION_BUY",
                "price": 88500.0 + i,
                "quantity": 0.001,
                "tx_hash": f"0x{i:064x}",
                "timestamp_ms": 1730900000000 + i,
            })
        assert len(hub.recent_executions) == 50
        assert hub.recent_executions[-1].price == 88559.0

    def test_guardrails_snapshot_update(self, hub):
        gs = hub.update_guardrails({
            "approved": True,
            "simulated_gas_used": 145000,
            "quoted_amount_out_min": 226000,
            "estimated_price_impact_pct": 0.45,
        })
        assert isinstance(gs, GuardrailStateSnapshot)
        assert hub.latest_guardrails.approved is True


# ===========================================================================
# 2. SSE Router & Streaming Unit Tests
# ===========================================================================

class TestSSERouting:
    def test_events_reasoning_endpoint_status(self, client):
        response = client.get("/events/reasoning?limit=1")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers.get("x-accel-buffering") == "no"
        assert ": connected" in response.text

    def test_api_deliberation_stream_alias(self, client):
        response = client.get("/api/deliberation/stream?limit=1")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert ": connected" in response.text

    def test_sse_backlog_replay_since_id(self, hub, client):
        for i in range(5):
            hub.publish_event("agent_thought", "Market Analyst", f"Historical Token {i}")

        response = client.get("/events/reasoning?since_id=3&limit=3")
        assert response.status_code == 200
        assert "Historical Token 4" in response.text

    def test_sse_last_event_id_header(self, hub, client):
        for i in range(4):
            hub.publish_event("agent_thought", "Market Analyst", f"Event Token {i}")

        response = client.get("/events/reasoning?limit=3", headers={"Last-Event-ID": "2"})
        assert response.status_code == 200
        assert "Event Token 3" in response.text


# ===========================================================================
# 3. WebSocket Telemetry Unit Tests
# ===========================================================================

def _recv_type(ws, target_type, limit=10):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("message_type") == target_type:
            return msg
    return msg


class TestWebSocketTelemetry:
    def test_ws_connection_and_initial_state_replay(self, client):
        with client.websocket_connect("/ws/telemetry") as ws:
            first_msg = ws.receive_json()
            assert first_msg["channel"] == "websocket"
            assert first_msg["message_type"] in ["ticker_update", "orderbook_snapshot", "guardrail_state"]

    def test_ws_heartbeat_ping_pong(self, client):
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.send_json({"type": "ping", "timestamp": 123456789})
            resp = _recv_type(ws, "pong")
            assert resp["channel"] == "websocket"
            assert resp["message_type"] == "pong"
            assert resp["payload"]["client_timestamp"] == 123456789
            assert resp["payload"]["server_time_ms"] > 0

    def test_ws_channel_subscription_and_ack(self, client):
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.send_json({"type": "subscribe", "channels": ["ticker", "orderbook"]})
            ack = _recv_type(ws, "subscription_ack")
            assert ack["message_type"] == "subscription_ack"
            assert ack["payload"]["status"] == "subscribed"
            assert "ticker" in ack["payload"]["channels"]

    def test_ws_channel_unsubscription_ack(self, client):
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.send_json({"type": "unsubscribe", "channels": ["orderbook"]})
            ack = _recv_type(ws, "subscription_ack")
            assert ack["message_type"] == "subscription_ack"
            assert ack["payload"]["status"] == "unsubscribed"

    def test_ws_multi_client_broadcast(self, client, hub):
        with client.websocket_connect("/ws/telemetry") as ws1:
            with client.websocket_connect("/ws/telemetry") as ws2:
                hub.record_execution({
                    "type": "EXECUTION_BUY",
                    "price": 88500.0,
                    "quantity": 0.05,
                    "tx_hash": "0xabc1234567890",
                    "timestamp_ms": 1730900000000,
                })

                msg1 = _recv_type(ws1, "execution_marker")
                msg2 = _recv_type(ws2, "execution_marker")
                assert msg1["message_type"] == "execution_marker"
                assert msg2["message_type"] == "execution_marker"
                assert msg1["payload"]["tx_hash"] == "0xabc1234567890"


# ===========================================================================
# 4. FastAPI Server Endpoints Unit Tests
# ===========================================================================

class TestFastAPIServerEndpoints:
    def test_health_check_payload_contract(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "trading-visualization"
        assert data["version"] == "1.0.0"

    def test_api_health_alias(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_server_status_endpoint(self, client):
        res = client.get("/status")
        assert res.status_code == 200
        data = res.json()
        assert data["service"] == "trading-visualization"
        assert data["status"] == "online"
        assert data["active_port"] == DEFAULT_PORT
        assert "connected_ws_clients" in data

    def test_cors_headers_presence(self, client):
        res = client.options("/health", headers={"Origin": "http://localhost:8899", "Access-Control-Request-Method": "GET"})
        assert res.headers.get("access-control-allow-origin") == "*"

    def test_orderbook_rest_snapshot(self, client):
        res = client.get("/api/orderbook")
        assert res.status_code == 200
        book = res.json()
        assert book["symbol"] == "BTC/USDT"
        assert len(book["bids"]) > 0
        assert len(book["asks"]) > 0
        assert book["bids"][0][0] > book["bids"][1][0]  # Descending
        assert book["asks"][0][0] < book["asks"][1][0]  # Ascending

    def test_root_serves_html_dashboard(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "Antigravity Trading Terminal" in res.text
        assert "candleChart" in res.text

    def test_static_css_asset_serving(self, client):
        res = client.get("/static/css/dashboard.css")
        assert res.status_code == 200
        assert "text/css" in res.headers["content-type"]
        assert "--bg-base" in res.text

    def test_static_js_chart_engine_serving(self, client):
        res = client.get("/static/js/chart_engine.js")
        assert res.status_code == 200
        assert "CanvasChartEngine" in res.text

    def test_static_js_app_serving(self, client):
        res = client.get("/static/js/app.js")
        assert res.status_code == 200
        assert "initChart" in res.text

    def test_metamask_stage_and_confirm_transaction(self, client):
        stage_res = client.post("/send-transaction", json={
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 200000000,
            "amount_out_min_wei": 226000,
            "chain_id": 42161,
            "trade_value_usd": 200.0,
        })
        assert stage_res.status_code == 200
        req_id = stage_res.json()["request_id"]
        assert req_id is not None

        confirm_res = client.post("/confirm-transaction", json={
            "request_id": req_id,
            "tx_hash": "0xdeadbeef1234567890abcdef",
            "success": True,
        })
        assert confirm_res.status_code == 200
        assert confirm_res.json()["tx_hash"] == "0xdeadbeef1234567890abcdef"

    def test_design_review_quality_endpoint(self, client):
        res = client.get("/api/design/review")
        assert res.status_code == 200
        data = res.json()
        assert data["passed"] is True
        assert data["composite_score"] >= 3.0
        assert data["ready_to_ship"] is True


# ===========================================================================
# 5. ReasoningStreamCallbackHandler Unit Tests
# ===========================================================================

class TestReasoningStreamCallbackHandler:
    def test_callback_on_llm_new_token(self, hub):
        handler = ReasoningStreamCallbackHandler(hub, default_role="Bull Researcher")
        handler.on_llm_new_token("TokenChunk1")
        handler.on_llm_new_token("TokenChunk2")
        assert len(hub.event_stream) == 2
        assert hub.event_stream[0].event == "agent_thought"
        assert hub.event_stream[0].agent_role == "Bull Researcher"
        assert hub.event_stream[1].token == "TokenChunk2"

    def test_callback_set_active_agent_and_round(self, hub):
        handler = ReasoningStreamCallbackHandler(hub)
        handler.set_active_agent("Bear Researcher", round_num=3)
        handler.on_llm_new_token("BearThesis")
        ev = hub.event_stream[-1]
        assert ev.agent_role == "Bear Researcher"
        assert ev.debate_round == 3

    def test_callback_on_tool_lifecycle(self, hub):
        handler = ReasoningStreamCallbackHandler(hub, default_role="Market Analyst")
        handler.on_tool_start({"name": "ccxt_fetch"}, "BTC/USDT")
        assert hub.event_stream[-1].event == "tool_call"
        assert "ccxt_fetch" in hub.event_stream[-1].token

        handler.on_tool_end({"price": 88500.0})
        assert hub.event_stream[-1].event == "tool_call"
        assert "88500.0" in hub.event_stream[-1].token

    def test_callback_publish_debate_and_proposals(self, hub):
        handler = ReasoningStreamCallbackHandler(hub)
        handler.publish_debate_turn("Bull Researcher", "Turn 1 Bull Argument", round_num=1)
        handler.publish_debate_argument("Bear Researcher", "Turn 1 Bear Rebuttal", round_num=1)
        handler.publish_proposal("Trader", {"action": "BUY", "symbol": "BTC/USDT", "entry_price": 88500.0})
        handler.publish_decision("Portfolio Manager", {"rating": "BUY", "price_target": 95000.0})
        handler.publish_trade_execution("Trader", {"tx_hash": "0x12345678", "gas_used": 145000})

        events = hub.event_stream
        assert len(events) == 5
        assert events[0].event == "debate_turn"
        assert events[1].event == "debate_argument"
        assert events[2].event == "proposal_generated"
        assert events[3].event == "decision"
        assert events[4].event == "trade_telemetry"
