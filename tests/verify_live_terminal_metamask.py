"""Automated Verification Suite for Live AI Trading Terminal & MetaMask Bridge (Milestone 6).

Comprehensive verification of:
1. Health and System Status Endpoints
2. Production Auth Enforcement on Web Visualization Dashboard (/?token=... and /dashboard)
3. Zero-regression Development Mode Authentication Bypass
4. Full-Duplex WebSocket Telemetry (/ws/telemetry) with Heartbeat, Subscriptions, and Indicator Updates
5. Server-Sent Events Reasoning Stream (/events/reasoning) with Multi-Agent Deliberation and Backlog Replay
6. EIP-1193 MetaMask Bridge Endpoints (/wallet_syncAccount and /rpc)
7. Transaction Staging, Confirmation, and Rejection Lifecycle (/send-transaction & /confirm-transaction)
8. Multi-Asset (BTC, ETH, SOL) Technical Indicators and Quant Telemetry Schema

Run as standalone script:
    python tests/verify_live_terminal_metamask.py
Run via pytest:
    python -m pytest tests/verify_live_terminal_metamask.py -v
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from starlette.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import run_live_metamask_terminal
from run_live_metamask_terminal import (
    ASSET_CONFIGS,
    LIVE_SESSION_TOKEN,
    build_live_app,
)
from visualization.server.app import create_visualization_app
from visualization.server.models import (
    ChartCandle,
    OrderBookSnapshot,
    TechnicalIndicators,
)
from visualization.telemetry.hub import TelemetryHub


# ==============================================================================
# Helper Functions & Test App Builders
# ==============================================================================

def get_prod_client() -> tuple[TestClient, Any]:
    """Build a production-mode live terminal app and TestClient."""
    os.environ["TRADINGAGENTS_SECURITY_MODE"] = "production"
    os.environ["TRADING_API_KEY"] = LIVE_SESSION_TOKEN
    app = build_live_app()
    client = TestClient(app)
    return client, app


def get_dev_client() -> tuple[TestClient, Any]:
    """Build a default development-mode app and TestClient with auth bypassed."""
    os.environ.pop("TRADINGAGENTS_SECURITY_MODE", None)
    os.environ.pop("TRADING_API_KEY", None)
    app = create_visualization_app()
    client = TestClient(app)
    return client, app


# ==============================================================================
# Verification Test Cases
# ==============================================================================

def test_health_endpoints():
    """Verify that health check endpoints remain public and return 200 OK."""
    client, _ = get_prod_client()

    resp_health = client.get("/health")
    assert resp_health.status_code == 200, f"Expected 200, got {resp_health.status_code}"
    data_health = resp_health.json()
    assert data_health.get("status") == "ok", f"Expected status 'ok', got {data_health}"

    resp_api_health = client.get("/api/health")
    assert resp_api_health.status_code == 200
    assert resp_api_health.json().get("status") == "ok"

    resp_status = client.get("/status")
    assert resp_status.status_code == 200
    assert resp_status.json().get("service") == "trading-visualization"


def test_dashboard_token_auth_enforcement():
    """Verify that dashboard endpoints (/ and /dashboard) enforce auth in production mode."""
    client, _ = get_prod_client()
    valid_token = LIVE_SESSION_TOKEN

    # 1. Valid token in query string -> 200 OK HTML
    resp_valid = client.get(f"/?token={valid_token}")
    assert resp_valid.status_code == 200, f"Expected 200 with valid token, got {resp_valid.status_code}"
    assert "text/html" in resp_valid.headers.get("content-type", "")
    assert "Antigravity Trading Terminal" in resp_valid.text or "candleChart" in resp_valid.text

    resp_valid_dash = client.get(f"/dashboard?token={valid_token}")
    assert resp_valid_dash.status_code == 200
    assert "text/html" in resp_valid_dash.headers.get("content-type", "")

    # 2. Missing token -> 401 Unauthorized
    resp_missing = client.get("/")
    assert resp_missing.status_code == 401, f"Expected 401 without token, got {resp_missing.status_code}"

    resp_missing_dash = client.get("/dashboard")
    assert resp_missing_dash.status_code == 401, f"Expected 401 without token, got {resp_missing_dash.status_code}"

    # 3. Invalid token -> 401 Unauthorized
    resp_invalid = client.get("/?token=invalid_fake_token_xyz")
    assert resp_invalid.status_code == 401, f"Expected 401 with bad token, got {resp_invalid.status_code}"

    resp_invalid_dash = client.get("/dashboard?token=invalid_fake_token_xyz")
    assert resp_invalid_dash.status_code == 401, f"Expected 401 with bad token, got {resp_invalid_dash.status_code}"

    # 4. Bearer authorization header works as well
    resp_bearer = client.get("/", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp_bearer.status_code == 200


def test_dashboard_dev_mode_bypass():
    """Verify that in default development mode, dashboard requests succeed with zero regression."""
    client, _ = get_dev_client()

    resp_dev_root = client.get("/")
    assert resp_dev_root.status_code == 200, f"Dev mode should return 200, got {resp_dev_root.status_code}"
    assert "text/html" in resp_dev_root.headers.get("content-type", "")

    resp_dev_dash = client.get("/dashboard")
    assert resp_dev_dash.status_code == 200
    assert "text/html" in resp_dev_dash.headers.get("content-type", "")


def recv_type(ws, target_type: str, limit: int = 10) -> Dict[str, Any]:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("message_type") == target_type:
            return msg
    return msg


def test_websocket_telemetry_streaming():
    """Verify WebSocket /ws/telemetry authentication, initial state sync, heartbeat, and live updates."""
    client, app = get_prod_client()
    hub: TelemetryHub = app.state.telemetry_hub
    valid_token = LIVE_SESSION_TOKEN

    # 1. Connect with valid token
    with client.websocket_connect(f"/ws/telemetry?token={valid_token}") as ws:
        # Initial cached messages are delivered on connection
        first_msg = ws.receive_json()
        assert first_msg.get("channel") == "websocket"
        assert first_msg.get("message_type") in ["ticker_update", "orderbook_snapshot", "guardrail_state"]

        # 2. Ping-pong heartbeat
        client_ts = int(time.time() * 1000)
        ws.send_json({"type": "ping", "timestamp": client_ts})
        pong_msg = recv_type(ws, "pong")
        assert pong_msg.get("message_type") == "pong"
        assert pong_msg.get("payload", {}).get("client_timestamp") == client_ts
        assert "server_time_ms" in pong_msg.get("payload", {})

        # 3. Channel subscription ack
        ws.send_json({"type": "subscribe", "channels": ["ticker", "indicators"]})
        sub_ack = recv_type(ws, "subscription_ack")
        assert sub_ack.get("message_type") == "subscription_ack"
        assert sub_ack.get("payload", {}).get("status") == "subscribed"
        assert "ticker" in sub_ack.get("payload", {}).get("channels", [])

        # 4. Trigger live indicator update with multi-asset schema
        ind = TechnicalIndicators(
            symbol="BTC/USDT",
            ema_20=88200.5,
            macd=45.2,
            rsi_14=61.4,
            atr_14=320.0,
            adx_14=28.5,
            sma_20=88150.0,
            ema_50=87900.0,
        )
        hub.update_indicators(ind)

        # Receive dispatched indicator update frame
        ind_msg = recv_type(ws, "indicator_update")
        assert ind_msg.get("message_type") == "indicator_update"
        payload = ind_msg.get("payload", {})
        assert payload.get("symbol") == "BTC/USDT"
        assert payload.get("rsi_14") == 61.4
        assert payload.get("adx_14") == 28.5
        assert payload.get("sma_20") == 88150.0
        assert payload.get("ema_50") == 87900.0


def test_sse_reasoning_stream():
    """Verify Server-Sent Events /events/reasoning auth and live deliberation streaming."""
    client, app = get_prod_client()
    hub: TelemetryHub = app.state.telemetry_hub
    valid_token = LIVE_SESSION_TOKEN

    # 1. Missing token -> 401
    resp_unauth = client.get("/events/reasoning?limit=1")
    assert resp_unauth.status_code == 401

    # 2. Invalid token -> 401
    resp_bad = client.get("/events/reasoning?token=wrong_token&limit=1")
    assert resp_bad.status_code == 401

    # 3. Publish mock deliberation events into hub
    hub.publish_event(
        "tool_call",
        "Market Analyst",
        "Live Spot Feed BTC/USDT: $88,500 | RSI(14)=62.1",
        snapshot={"price": 88500.0, "rsi": 62.1},
    )
    hub.publish_event(
        "proposal_generated",
        "Execution Trader",
        "PROPOSAL READY: BUY 0.000452 BTC ($40.00)",
        snapshot={"action": "BUY", "symbol": "BTC/USDT"},
    )

    # 4. Connect to SSE stream with valid token and fetch delivered frames (replaying from since_id=0)
    resp_sse = client.get(f"/events/reasoning?token={valid_token}&since_id=0&limit=3")
    assert resp_sse.status_code == 200
    assert "text/event-stream" in resp_sse.headers.get("content-type", "")
    assert ": connected" in resp_sse.text
    assert "Market Analyst" in resp_sse.text
    assert "Execution Trader" in resp_sse.text


def test_bridge_wallet_sync_and_rpc():
    """Verify MetaMask bridge endpoints /wallet_syncAccount and /rpc."""
    client, app = get_prod_client()
    valid_token = LIVE_SESSION_TOKEN
    headers = {"Authorization": f"Bearer {valid_token}"}
    test_account = "0x71C836e520D756c22B69a23B9781Dfe4842d3c12"

    # 1. Direct /wallet_syncAccount with integer chain_id
    sync_res = client.post(
        "/wallet_syncAccount",
        json={"account": test_account, "chain_id": 42161},
        headers=headers,
    )
    assert sync_res.status_code == 200
    data = sync_res.json()
    assert data["status"] == "synchronized"
    assert test_account in data["connected_accounts"]
    assert data["chain_id"] == 42161

    # 2. Direct /wallet_syncAccount with hex chain_id ("0xa4b1" = 42161)
    hex_account = "0x28C6c06298d514Db089934071355E5743bf21d60"
    sync_hex = client.post(
        "/wallet_syncAccount",
        json={"account": hex_account, "chain_id": "0xa4b1"},
        headers=headers,
    )
    assert sync_hex.status_code == 200
    assert hex_account in sync_hex.json()["connected_accounts"]
    assert sync_hex.json()["chain_id"] == 42161

    # 3. JSON-RPC /rpc wallet_syncAccount
    rpc_account = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    rpc_res = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 101,
            "method": "wallet_syncAccount",
            "params": [rpc_account, 42161],
        },
        headers=headers,
    )
    assert rpc_res.status_code == 200
    assert rpc_account in rpc_res.json()["result"]

    # 4. JSON-RPC standard methods
    res_accounts = client.post("/rpc", json={"jsonrpc": "2.0", "id": 102, "method": "eth_accounts"}, headers=headers)
    assert res_accounts.status_code == 200
    assert rpc_account in res_accounts.json()["result"]

    res_chain = client.post("/rpc", json={"jsonrpc": "2.0", "id": 103, "method": "eth_chainId"}, headers=headers)
    assert res_chain.status_code == 200
    assert res_chain.json()["result"] == "0xa4b1"

    res_net = client.post("/rpc", json={"jsonrpc": "2.0", "id": 104, "method": "net_version"}, headers=headers)
    assert res_net.status_code == 200
    assert res_net.json()["result"] == "42161"


def test_bridge_transaction_lifecycle_confirm_and_reject():
    """Verify transaction staging, confirmation, and rejection handling."""
    client, app = get_prod_client()
    valid_token = LIVE_SESSION_TOKEN
    headers = {"Authorization": f"Bearer {valid_token}"}

    # 1. Stage a transaction
    stage_res = client.post(
        "/send-transaction",
        json={
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 100000000,
            "amount_out_min_wei": 113000,
            "chain_id": 42161,
            "trade_value_usd": 100.0,
        },
        headers=headers,
    )
    assert stage_res.status_code == 200
    stage_data = stage_res.json()
    assert stage_data["status"] == "staged"
    req_id_1 = stage_data["request_id"]
    assert req_id_1.startswith("tx_")

    # 2. Confirm the transaction (success=True)
    tx_hash = "0x" + "c0ffee" * 10 + "0000"
    confirm_res = client.post(
        "/confirm-transaction",
        json={"request_id": req_id_1, "tx_hash": tx_hash, "success": True},
        headers=headers,
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "confirmed"
    assert confirm_res.json()["tx_hash"] == tx_hash

    # 3. Stage a second transaction to reject
    stage_res_2 = client.post(
        "/send-transaction",
        json={
            "to": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "amount_in_wei": 50000000,
            "trade_value_usd": 50.0,
        },
        headers=headers,
    )
    assert stage_res_2.status_code == 200
    req_id_2 = stage_res_2.json()["request_id"]

    # 4. Reject transaction (success=False)
    reject_reason = "MetaMask: User denied transaction signature."
    reject_res = client.post(
        "/confirm-transaction",
        json={
            "request_id": req_id_2,
            "success": False,
            "error_reason": reject_reason,
        },
        headers=headers,
    )
    assert reject_res.status_code == 200
    rej_data = reject_res.json()
    assert rej_data["status"] == "rejected"
    assert rej_data["request_id"] == req_id_2

    # Verify bridge server state
    bridge = app.state.bridge_server
    assert req_id_2 in bridge.transaction_results
    assert bridge.transaction_results[req_id_2]["status"] == "rejected"
    assert bridge.transaction_results[req_id_2]["error_reason"] == reject_reason


def test_multi_asset_schema_and_configs():
    """Verify multi-asset configurations (BTC, ETH, SOL) and extended indicators schema."""
    # 1. Verify ASSET_CONFIGS contains BTC, ETH, and SOL
    symbols = [cfg["symbol"] for cfg in ASSET_CONFIGS]
    pairs = [cfg["pair"] for cfg in ASSET_CONFIGS]
    assert "BTC/USDT" in symbols
    assert "ETH/USDT" in symbols
    assert "SOL/USDT" in symbols
    assert "BTC-USD" in pairs
    assert "ETH-USD" in pairs
    assert "SOL-USD" in pairs

    # 2. Verify TechnicalIndicators model fields
    model_fields = TechnicalIndicators.model_fields
    assert "adx_14" in model_fields
    assert "sma_20" in model_fields
    assert "ema_50" in model_fields
    assert "ema_20" in model_fields
    assert "macd" in model_fields
    assert "rsi_14" in model_fields

    # 3. Instantiate with all fields and check serialization
    indicators = TechnicalIndicators(
        symbol="SOL/USDT",
        ema_20=194.2,
        macd=1.85,
        rsi_14=54.2,
        atr_14=4.25,
        adx_14=31.0,
        sma_20=193.5,
        ema_50=191.0,
    )
    dumped = indicators.model_dump()
    assert dumped["adx_14"] == 31.0
    assert dumped["sma_20"] == 193.5
    assert dumped["ema_50"] == 191.0


# ==============================================================================
# Standalone Runner
# ==============================================================================

def run_all_verifications() -> int:
    """Run all verification tests sequentially and print structured results."""
    print("=" * 80)
    print(" ANTIGRAVITY LIVE TERMINAL & METAMASK BRIDGE VERIFICATION HARNESS")
    print("=" * 80)
    tests = [
        ("Health Endpoints Contract", test_health_endpoints),
        ("Dashboard Token Authentication Gate (R1)", test_dashboard_token_auth_enforcement),
        ("Development Mode Zero-Regression Check", test_dashboard_dev_mode_bypass),
        ("Full-Duplex WebSocket Telemetry & Heartbeat (R2)", test_websocket_telemetry_streaming),
        ("SSE Reasoning Deliberation Stream (R2)", test_sse_reasoning_stream),
        ("MetaMask Bridge Wallet Sync & JSON-RPC (R3)", test_bridge_wallet_sync_and_rpc),
        ("Transaction Staging, Confirm & Rejection Lifecycle (R3)", test_bridge_transaction_lifecycle_confirm_and_reject),
        ("Multi-Asset Feed Config & Indicators Schema (R2)", test_multi_asset_schema_and_configs),
    ]

    passed = 0
    start_time = time.time()
    for name, test_fn in tests:
        print(f"[*] Running: {name} ...", end=" ", flush=True)
        try:
            test_fn()
            print("[PASS]")
            passed += 1
        except Exception as e:
            print("[FAIL]")
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1

    elapsed = time.time() - start_time
    print("=" * 80)
    print(f" VERIFICATION RESULT: {passed}/{len(tests)} TESTS PASSED ({elapsed:.2f}s)")
    print(" ALL METAMASK BRIDGE & LIVE TERMINAL GATES 100% OPERATIONAL")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_all_verifications())
