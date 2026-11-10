"""
Adversarial Stress & Edge Case Verification Suite for Live Endpoints (Milestone 6).

Adversarially probes:
1. Auth Gate Resilience (GET /, GET /dashboard, GET /events/reasoning, WS /ws/telemetry)
   - Malformed, expired, forged, non-ASCII, empty, truncated, and injected tokens.
2. Rate Limiting Burst Stress (POST /wallet_syncAccount)
   - Rapid burst requests, token bucket saturation (30 limit), and concurrent thread safety.
3. WebSocket Handshake & Concurrency Stress (WS /ws/telemetry)
   - Rapid connect/disconnect cycles, concurrent persistent connections, frame fuzzing.
4. Payload Fuzzing & Input Boundary Violations (POST /wallet_syncAccount, POST /rpc, POST /confirm-transaction)
   - Non-dict JSON payloads, non-scalar chain IDs, non-hex address injection, negative chain IDs.
"""
from __future__ import annotations

import concurrent.futures
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_live_metamask_terminal import LIVE_SESSION_TOKEN, build_live_app
from visualization.server.app import create_visualization_app
from visualization.server.security import global_rate_limiter, global_simulation_cache
from visualization.telemetry.hub import TelemetryHub


@pytest.fixture(autouse=True)
def reset_security_state():
    """Reset rate limiter and simulation cache between tests."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()


@pytest.fixture
def prod_client():
    """Create production mode TestClient."""
    os.environ["TRADINGAGENTS_SECURITY_MODE"] = "production"
    os.environ["TRADING_API_KEY"] = LIVE_SESSION_TOKEN
    app = build_live_app()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def dev_client():
    """Create development mode TestClient with auth bypassed."""
    os.environ.pop("TRADINGAGENTS_SECURITY_MODE", None)
    os.environ.pop("TRADING_API_KEY", None)
    app = create_visualization_app()
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. Auth Gate Resilience & Token Edge Cases
# ==============================================================================

class TestAuthGateAdversarial:
    """Stress tests production token authentication across all protected endpoints."""

    HOSTILE_TOKENS = [
        "",
        "   ",
        "wrong_token_12345",
        "ag_live_metamask_2026_toke",         # 1-char truncated
        "ag_live_metamask_2026_token_extra",   # Appended
        "AG_LIVE_METAMASK_2026_TOKEN",         # Case mismatch
        "ag_live_metamask_2026_token%00",     # Null byte injected
        "\U0001F511",                          # Unicode emoji
        "A" * 4096,                            # Buffer overflow
        "' OR '1'='1",                         # SQLi
        "<script>alert(1)</script>",           # XSS tag
    ]

    @pytest.mark.parametrize("token", HOSTILE_TOKENS)
    def test_dashboard_rejects_hostile_tokens(self, prod_client, token):
        # Test GET /
        res_root = prod_client.get(f"/?token={token}")
        assert res_root.status_code == 401, f"GET / allowed hostile token {repr(token)}"

        # Test GET /dashboard
        res_dash = prod_client.get(f"/dashboard?token={token}")
        assert res_dash.status_code == 401, f"GET /dashboard allowed hostile token {repr(token)}"

    @pytest.mark.parametrize("token", HOSTILE_TOKENS)
    def test_sse_reasoning_rejects_hostile_tokens(self, prod_client, token):
        res_sse = prod_client.get(f"/events/reasoning?token={token}&limit=1")
        assert res_sse.status_code == 401, f"GET /events/reasoning allowed hostile token {repr(token)}"

    @pytest.mark.parametrize("token", HOSTILE_TOKENS)
    def test_ws_telemetry_rejects_hostile_tokens(self, prod_client, token):
        try:
            with prod_client.websocket_connect(f"/ws/telemetry?token={token}"):
                pytest.fail(f"WS /ws/telemetry handshake succeeded with hostile token {repr(token)}")
        except (WebSocketDisconnect, Exception) as exc:
            pass  # Expected rejection

    def test_valid_token_accepted_on_all_endpoints(self, prod_client):
        token = LIVE_SESSION_TOKEN
        # 1. GET /
        res_root = prod_client.get(f"/?token={token}")
        assert res_root.status_code == 200
        assert "text/html" in res_root.headers.get("content-type", "")

        # 2. GET /dashboard
        res_dash = prod_client.get(f"/dashboard?token={token}")
        assert res_dash.status_code == 200

        # 3. GET /events/reasoning
        res_sse = prod_client.get(f"/events/reasoning?token={token}&limit=1")
        assert res_sse.status_code == 200
        assert "text/event-stream" in res_sse.headers.get("content-type", "")

        # 4. WS /ws/telemetry
        with prod_client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
            msg = ws.receive_json()
            assert "channel" in msg or "message_type" in msg


# ==============================================================================
# 2. Rate Limiting Burst Stress
# ==============================================================================

class TestRateLimitingBurstStress:
    """Stress tests DoS rate limiter on /wallet_syncAccount under burst conditions."""

    def test_wallet_sync_burst_rate_limiting(self, prod_client):
        """30 requests succeed; 31st through 40th must return HTTP 429."""
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {"account": "0x1234567890123456789012345678901234567890", "chain_id": 42161}

        statuses = [
            prod_client.post("/wallet_syncAccount", json=payload, headers=headers).status_code
            for _ in range(40)
        ]

        allowed_count = statuses.count(200)
        rate_limited_count = statuses.count(429)

        assert allowed_count == 30, f"Expected 30 allowed requests, got {allowed_count}"
        assert rate_limited_count == 10, f"Expected 10 rate-limited requests, got {rate_limited_count}"
        assert statuses[:30] == [200] * 30
        assert statuses[30:] == [429] * 10

    def test_wallet_sync_concurrent_burst_thread_safety(self, prod_client):
        """Concurrent requests across threads adhere to token bucket invariant."""
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {"account": "0x1234567890123456789012345678901234567890", "chain_id": 42161}

        def send_req(_):
            return prod_client.post("/wallet_syncAccount", json=payload, headers=headers).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(send_req, range(40)))

        allowed = sum(1 for s in results if s == 200)
        denied = sum(1 for s in results if s == 429)

        assert allowed == 30
        assert denied == 10


# ==============================================================================
# 3. WebSocket Handshake & Concurrency Stress
# ==============================================================================

class TestWebSocketConcurrencyStress:
    """Stress tests WebSocket telemetry endpoint under rapid and concurrent connections."""

    def test_rapid_connect_disconnect_cycles(self, prod_client):
        """20 rapid connect and disconnect cycles must not leak resources or crash."""
        token = LIVE_SESSION_TOKEN
        for i in range(20):
            with prod_client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
                ws.send_json({"type": "ping", "timestamp": i})
                # Read at least one frame
                msg = ws.receive_json()
                assert msg is not None

    def test_concurrent_connections_and_ping_pong(self, prod_client):
        """5 concurrent WebSocket connections send pings and receive responsive pongs."""
        token = LIVE_SESSION_TOKEN

        def worker(w_id: int):
            with prod_client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
                ws.receive_json()  # Read initial snapshot
                ws.send_json({"type": "ping", "timestamp": w_id})
                pong = None
                for _ in range(5):
                    m = ws.receive_json()
                    if m.get("message_type") == "pong":
                        pong = m
                        break
                assert pong is not None
                assert pong["payload"]["client_timestamp"] == w_id
            return w_id

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            completed = list(executor.map(worker, range(5)))
        assert len(completed) == 5

    def test_corrupt_frames_and_channel_injection_resilience(self, prod_client):
        """WebSocket connection remains alive when client sends corrupt or injection frames."""
        token = LIVE_SESSION_TOKEN
        with prod_client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
            # 1. Non-JSON string
            ws.send_text("!@#$%^&*()_NON_JSON_CORRUPT_PAYLOAD")

            # 2. Injection subscribe
            ws.send_json({
                "type": "subscribe",
                "channels": ["ticker", "malicious_admin_exec", "orderbook"],
            })

            # Read ack
            ack = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("message_type") == "subscription_ack":
                    ack = msg
                    break

            assert ack is not None
            assert "ticker" in ack["payload"]["channels"]
            assert "orderbook" in ack["payload"]["channels"]
            assert "malicious_admin_exec" not in ack["payload"]["channels"]


# ==============================================================================
# 4. Empirical Vulnerability Probes: Payload Fuzzing & Input Validation
# ==============================================================================

class TestEmpiricalPayloadAndValidationVulnerabilities:
    """
    Empirically documents vulnerabilities in payload parsing and input validation.
    Endpoints should return 400 Bad Request or 422 Unprocessable Entity on malformed
    inputs, but instead trigger unhandled 500 Internal Server Errors or store invalid state.
    """

    def test_vulnerability_wallet_sync_non_dict_payload_crash(self, prod_client):
        """
        FAILING CONDITION:
        When /wallet_syncAccount receives a JSON array or primitive,
        body.get(...) raises AttributeError, returning HTTP 500 instead of 400/422.
        """
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}

        # 1. JSON array payload
        res_list = prod_client.post("/wallet_syncAccount", json=["0x1234567890123456789012345678901234567890", 42161], headers=headers)
        # Proper API behavior is 400 or 422; 500 indicates unhandled exception crash.
        assert res_list.status_code != 500, (
            f"VULNERABILITY: /wallet_syncAccount crashed with 500 on list payload: {res_list.text}"
        )

    def test_vulnerability_wallet_sync_non_scalar_chain_id_crash(self, prod_client):
        """
        FAILING CONDITION:
        When chain_id is a non-scalar (list or dict), int(chain_id) raises TypeError,
        which is uncaught, causing an unhandled 500 Internal Server Error.
        """
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {
            "account": "0x1234567890123456789012345678901234567890",
            "chain_id": [1, 2],  # Non-scalar list
        }
        res = prod_client.post("/wallet_syncAccount", json=payload, headers=headers)
        assert res.status_code != 500, (
            f"VULNERABILITY: /wallet_syncAccount crashed with 500 on non-scalar chain_id: {res.text}"
        )

    def test_vulnerability_rpc_non_scalar_chain_id_crash(self, prod_client):
        """
        FAILING CONDITION:
        When /rpc receives method 'wallet_syncAccount' with a list chain_id in params[1],
        int(params[1]) raises uncaught TypeError, causing HTTP 500.
        """
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {
            "jsonrpc": "2.0",
            "method": "wallet_syncAccount",
            "params": ["0x1234567890123456789012345678901234567890", [1, 2]],
            "id": 1,
        }
        res = prod_client.post("/rpc", json=payload, headers=headers)
        assert res.status_code != 500, (
            f"VULNERABILITY: /rpc crashed with 500 on non-scalar params[1]: {res.text}"
        )

    def test_vulnerability_non_hex_account_accepted_without_validation(self, prod_client):
        """
        FAILING CONDITION:
        Non-hex strings (e.g. 'not_an_eth_address' or '<script>alert(1)</script>')
        are accepted into bridge connected_accounts and published in agent deliberation events.
        """
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {"account": "not_an_eth_address", "chain_id": 42161}
        res = prod_client.post("/wallet_syncAccount", json=payload, headers=headers)

        # A secure endpoint should reject non-hex addresses with 400/422
        assert res.status_code in [400, 422], (
            f"VULNERABILITY: /wallet_syncAccount accepted non-hex address 'not_an_eth_address' (status {res.status_code})"
        )

    def test_vulnerability_negative_chain_id_accepted_without_validation(self, prod_client):
        """
        FAILING CONDITION:
        Negative chain ID (e.g. -1 or -42161) violates EIP-155 but is accepted by the bridge.
        """
        headers = {"Authorization": f"Bearer {LIVE_SESSION_TOKEN}"}
        payload = {"account": "0x1234567890123456789012345678901234567890", "chain_id": -1}
        res = prod_client.post("/wallet_syncAccount", json=payload, headers=headers)

        # A secure endpoint should reject negative chain IDs with 400/422
        assert res.status_code in [400, 422], (
            f"VULNERABILITY: /wallet_syncAccount accepted invalid negative chain ID -1 (status {res.status_code})"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))
