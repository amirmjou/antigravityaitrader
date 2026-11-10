"""
Challenger 1: Empirical Auth & Transport Penetration Stress Testing Suite.
Empirically challenges the security controls on REST API, SSE deliberation stream,
and WebSocket interfaces against hostile attacks:
- Header manipulation & token tampering (SQLi, command injection, Unicode, buffer overflow, byte flipping)
- Unauthenticated transaction staging, confirmation, and JSON-RPC execution
- SSE deliberation stream subscription unauthorized attempts and CORS origin verification
- WebSocket handshake authorization attacks and malformed payload injection
- Hostile CORS origin spoofing (subdomain hijack, null origin, protocol manipulation)
- Rate limiting saturation under rapid burst conditions and multi-threaded concurrency
- Deep secret scrubbing and private key trace redaction
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import stat
import tempfile
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.dataflows.net import scrub_secrets, sanitize_secret_trace
from execution.wallet.eip1193_bridge import EIP1193BridgeServer, create_bridge_app
from execution.wallet.hot_signer import HotKeystoreSigner
from visualization.server.app import create_visualization_app
from visualization.server.security import (
    RateLimiter,
    SimulationCache,
    global_rate_limiter,
    global_simulation_cache,
    is_auth_enforced,
    is_production_mode,
    verify_token_string,
)
from visualization.telemetry.hub import TelemetryHub

TEST_VALID_KEY = "challenger_valid_key_super_secret_xyz123!"


@pytest.fixture(autouse=True)
def clean_security_env(monkeypatch):
    """Enforce clean state before and after each challenge."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    yield
    os.environ.pop("TRADINGAGENTS_SECURITY_MODE", None)
    os.environ.pop("TRADING_API_KEY", None)
    os.environ.pop("ALLOWED_ORIGINS", None)
    global_rate_limiter.reset()
    global_simulation_cache.clear()


@pytest.fixture
def prod_client(monkeypatch):
    """Creates a test client in strict production mode with configured secret."""
    monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
    monkeypatch.setenv("TRADING_API_KEY", TEST_VALID_KEY)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://trading.cloud.com,http://localhost:3000")
    hub = TelemetryHub()
    app = create_visualization_app(hub=hub)
    return TestClient(app)


# ===========================================================================
# 1. Header Manipulation, Token Tampering, & Injection Attacks
# ===========================================================================

class TestAdversarialHeaderAndTokenManipulation:
    """Stress tests Bearer token and header parser against hostile payloads."""

    @pytest.mark.parametrize("hostile_auth_header", [
        "",                                    # Empty string
        "Bearer",                              # Missing space and token
        "Bearer ",                             # Empty token with space
        "Bearer       ",                       # Whitespace token
        "Basic dXNlcjpwYXNz",                  # Basic auth attempt
        "Token xyz123",                        # Token scheme attempt
        "Digest username=foo",                 # Digest auth attempt
        f"Bearer {TEST_VALID_KEY[:-1]}",       # 1-character truncated key
        f"Bearer {TEST_VALID_KEY}X",           # Appended character
        f"Bearer X{TEST_VALID_KEY}",           # Prepended character
        f"Bearer {TEST_VALID_KEY.upper()}",    # Case inverted
        f"Bearer {TEST_VALID_KEY}\x00",        # Null byte injection
        "Bearer ' OR '1'='1",                  # SQLi classic
        "Bearer admin'--",                     # SQLi comment
        "Bearer $(whoami)",                    # Command injection
        "Bearer `id`",                         # Backtick command injection
        "Bearer ; cat /etc/passwd",            # Command chain
        "Bearer ../../../etc/shadow",          # Path traversal
        "Bearer " + "A" * 8192,                # Buffer overflow 8KB
    ])
    def test_tampered_and_injected_bearer_tokens_rejected(self, prod_client, hostile_auth_header):
        headers = {"Authorization": hostile_auth_header} if hostile_auth_header else {}
        res = prod_client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 401, f"Expected 401 for header '{hostile_auth_header}', got {res.status_code}"
        assert res.json()["detail"] == "Unauthorized"

    @pytest.mark.parametrize("hostile_api_key", [
        "",
        "   ",
        "wrong_api_key_123",
        f"{TEST_VALID_KEY}_extra",
        f"{TEST_VALID_KEY[:10]}",
        "' OR 1=1 --",
        "{{7*7}}",
        "${env:PATH}",
        "<script>alert(1)</script>",
    ])
    def test_tampered_x_api_key_headers_rejected(self, prod_client, hostile_api_key):
        headers = {"X-API-Key": hostile_api_key}
        res = prod_client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 401
        assert res.json()["detail"] == "Unauthorized"

    def test_conflicting_headers_resolution(self, prod_client):
        """When multiple auth methods are provided, invalid Bearer fails even if X-API-Key is valid."""
        # Bearer takes precedence in FastAPI security scheme. An invalid Bearer must not fall back to valid X-API-Key.
        headers = {
            "Authorization": "Bearer BAD_TOKEN",
            "X-API-Key": TEST_VALID_KEY,
        }
        res = prod_client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 401, "Invalid Bearer must not be bypassed by valid X-API-Key"

    def test_constant_time_token_verification_oracles(self, monkeypatch):
        """Verify token verification returns False on empty, None, and partial matches."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", "secret_anchor_key")

        assert verify_token_string("secret_anchor_key") is True
        assert verify_token_string("secret_anchor_key_extended") is False
        assert verify_token_string("secret_anchor_") is False
        assert verify_token_string("") is False
        assert verify_token_string(None) is False
        assert verify_token_string(" ") is False


# ===========================================================================
# 2. Unauthenticated Transaction Staging & RPC Execution Attacks
# ===========================================================================

class TestAdversarialTransactionAndRpcExecution:
    """Attacks on financial execution endpoints in production mode."""

    def test_unauthenticated_send_transaction_payloads(self, prod_client):
        """Hostile transactions submitted without credentials must be blocked before staging."""
        payloads = [
            {"to": "0x0000000000000000000000000000000000000000", "amount_in_wei": 10**18},
            {"to": "0x" + "f" * 40, "amount_in_wei": 0, "calldata": "0xa9059cbb"},
            {"to": "0x1234567890123456789012345678901234567890", "amount_in_wei": -100},
        ]
        for p in payloads:
            res = prod_client.post("/send-transaction", json=p)
            assert res.status_code == 401
            assert res.json()["detail"] == "Unauthorized"

    def test_unauthenticated_confirm_transaction_tampering(self, prod_client):
        """Hostile caller attempting to fake a transaction confirmation without credentials."""
        res = prod_client.post(
            "/confirm-transaction",
            json={"request_id": "staged_req_001", "tx_hash": "0x" + "a" * 64, "success": True},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Unauthorized"

    def test_unauthenticated_json_rpc_methods(self, prod_client):
        """Test all standard Web3 JSON-RPC methods without credentials."""
        methods = [
            ("eth_sendTransaction", [{"to": "0x1234567890123456789012345678901234567890", "value": "0x100"}]),
            ("eth_accounts", []),
            ("eth_requestAccounts", []),
            ("eth_chainId", []),
            ("net_version", []),
            ("eth_blockNumber", []),
            ("nonexistent_method", []),
        ]
        for method, params in methods:
            res = prod_client.post("/rpc", json={"jsonrpc": "2.0", "method": method, "params": params, "id": 42})
            assert res.status_code == 401, f"RPC method {method} was not blocked with 401"

    def test_bridge_app_send_transaction_without_credentials(self, monkeypatch):
        """Attacking the standalone EIP-1193 bridge server directly."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_VALID_KEY)
        server = EIP1193BridgeServer()
        client = TestClient(server.app)

        res = client.post("/send-transaction", json={"to": "0x" + "1" * 40, "amount_in_wei": 100})
        assert res.status_code == 401

        res_sign = client.post("/sign-typed-data", json={"types": {}, "primaryType": "Mail", "message": {}})
        assert res_sign.status_code == 401

        res_confirm = client.post("/confirm-transaction", json={"request_id": "any", "tx_hash": "0x123"})
        assert res_confirm.status_code == 401

        res_rpc = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_sendTransaction", "params": [{}], "id": 1})
        assert res_rpc.status_code == 401


# ===========================================================================
# 3. SSE Deliberation Stream Unauthorized Access & CORS Attacks
# ===========================================================================

class TestAdversarialSseStreaming:
    """Stress testing the multi-agent deliberation SSE stream."""

    @pytest.mark.parametrize("endpoint", ["/events/reasoning", "/api/deliberation/stream"])
    def test_sse_endpoint_unauthenticated_rejection(self, prod_client, endpoint):
        res = prod_client.get(f"{endpoint}?limit=1")
        assert res.status_code == 401

    @pytest.mark.parametrize("tampered_token", [
        "wrong_token",
        "bearer_without_key",
        "12345",
        "'; DROP TABLE events;--",
    ])
    def test_sse_endpoint_tampered_query_token_rejection(self, prod_client, tampered_token):
        res = prod_client.get(f"/events/reasoning?token={tampered_token}&limit=1")
        assert res.status_code == 401

    def test_sse_endpoint_authenticated_success(self, prod_client):
        res = prod_client.get(f"/events/reasoning?token={TEST_VALID_KEY}&limit=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

    def test_sse_cors_rejection_from_hostile_origin(self, prod_client):
        """Hostile site attempting to cross-origin subscribe to agent reasoning stream."""
        headers = {
            "Origin": "https://evil-attacker.com",
            "Authorization": f"Bearer {TEST_VALID_KEY}",
        }
        res = prod_client.get("/events/reasoning?limit=1", headers=headers)
        # Even if token is valid, origin must not be reflected
        assert res.headers.get("access-control-allow-origin") != "https://evil-attacker.com"
        assert res.headers.get("access-control-allow-origin") != "*"

    def test_sse_cors_acceptance_from_trusted_origin(self, prod_client):
        """Trusted origin receives matching Access-Control-Allow-Origin."""
        headers = {
            "Origin": "https://trading.cloud.com",
            "Authorization": f"Bearer {TEST_VALID_KEY}",
        }
        res = prod_client.get("/events/reasoning?limit=1", headers=headers)
        assert res.headers.get("access-control-allow-origin") == "https://trading.cloud.com"
        assert res.headers.get("access-control-allow-credentials") == "true"


# ===========================================================================
# 4. WebSocket Handshake & Telemetry Frame Injection Attacks
# ===========================================================================

class TestAdversarialWebSocketHandshake:
    """Penetration tests against WebSocket telemetry and bridge connections."""

    @pytest.mark.parametrize("hostile_param", [
        "",
        "?token=",
        "?token=wrong_key_xyz",
        "?token=123",
        "?token=' OR 1=1 --",
        "?token=<script>alert(1)</script>",
        "?token=" + "A" * 4096,
    ])
    def test_ws_telemetry_unauthorized_handshake_rejected(self, prod_client, hostile_param):
        path = f"/ws/telemetry{hostile_param}"
        with pytest.raises((WebSocketDisconnect, Exception)):
            with prod_client.websocket_connect(path):
                pytest.fail("WebSocket handshake should have been disconnected with 1008")

    def test_ws_bridge_unauthorized_handshake_rejected(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_VALID_KEY)
        server = EIP1193BridgeServer()
        client = TestClient(server.app)

        with pytest.raises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws"):
                pytest.fail("EIP-1193 bridge WebSocket should have been disconnected without token")

    def test_ws_telemetry_authorized_and_frame_resilience(self, prod_client):
        """Authorized WebSocket handles corrupt frames and disallowed channel subscriptions gracefully."""
        with prod_client.websocket_connect(f"/ws/telemetry?token={TEST_VALID_KEY}") as ws:
            # 1. Send non-JSON junk bytes / strings -> should not crash
            ws.send_text("CORRUPT_NON_JSON_BYTES_!@#$%^&*()")

            # 2. Subscribe to forbidden / injected channels
            ws.send_json({
                "type": "subscribe",
                "channels": ["all", "injected_admin_shell", "os_exec", "guardrails"],
            })

            # Read frames until subscription_ack
            ack = None
            for _ in range(10):
                msg = ws.receive_json()
                if msg.get("message_type") == "subscription_ack":
                    ack = msg
                    break

            assert ack is not None, "Did not receive subscription_ack"
            assert "all" in ack["payload"]["channels"]
            assert "guardrails" in ack["payload"]["channels"]
            assert "injected_admin_shell" not in ack["payload"]["channels"]
            assert "os_exec" not in ack["payload"]["channels"]

            # 3. Valid ping -> pong
            ws.send_json({"type": "ping", "timestamp": 123456789})
            pong = None
            for _ in range(5):
                msg = ws.receive_json()
                if msg.get("message_type") == "pong":
                    pong = msg
                    break

            assert pong is not None, "Did not receive pong"
            assert pong["payload"]["client_timestamp"] == 123456789


# ===========================================================================
# 5. Hostile CORS Origin Spoofing & Header Attacks
# ===========================================================================

class TestHostileCorsAndHeaderAttacks:
    """Tests CORS preflight against various origin forgery techniques."""

    @pytest.mark.parametrize("hostile_origin", [
        "https://evil-hacker.com",
        "http://evil-hacker.com",
        "https://trading.cloud.com.evil.com",       # Subdomain suffix hijack
        "https://evil.com/trading.cloud.com",       # Path traversal in origin
        "http://localhost:3000.evil.com",          # Localhost subdomain suffix
        "null",                                     # Sandboxed iframe / file URI
        "http://127.0.0.1.evil.com",
    ])
    def test_cors_preflight_blocks_forged_origins(self, prod_client, hostile_origin):
        res = prod_client.options(
            "/rpc",
            headers={
                "Origin": hostile_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        # Hostile origin must NOT be reflected
        reflected = res.headers.get("access-control-allow-origin")
        assert reflected != hostile_origin, f"Hostile origin '{hostile_origin}' was dangerously reflected!"
        assert reflected != "*", "Wildcard '*' must never be returned in production mode!"

    def test_strict_security_headers_present_on_error_responses(self, prod_client):
        """Security headers (nosniff, DENY, HSTS, CSP) must be present even on 401/404 responses."""
        res_401 = prod_client.get("/api/performance/100-trades")
        assert res_401.status_code == 401
        assert res_401.headers.get("x-content-type-options") == "nosniff"
        assert res_401.headers.get("x-frame-options") == "DENY"
        assert "Strict-Transport-Security" in res_401.headers
        assert "Content-Security-Policy" in res_401.headers


# ===========================================================================
# 6. Rate Limiting Saturation & Multi-Threaded Stress
# ===========================================================================

class TestRateLimitingSaturationAndConcurrency:
    """Stress tests DoS rate limiting logic and thread safety."""

    def test_rate_limiter_simulation_hard_cutoff(self, prod_client):
        """5 simulation calls allowed; 6th through 10th must strictly return 429."""
        headers = {"Authorization": f"Bearer {TEST_VALID_KEY}"}
        status_codes = []
        for _ in range(8):
            res = prod_client.get("/api/performance/100-trades", headers=headers)
            status_codes.append(res.status_code)

        assert status_codes[:5] == [200, 200, 200, 200, 200]
        assert status_codes[5:] == [429, 429, 429]

    def test_rate_limiter_multithreaded_concurrency(self):
        """Concurrent requests across 20 threads safely decrement token bucket without race conditions."""
        limiter = RateLimiter()
        limit = 15
        key = "test_ip_127.0.0.1"

        results = []

        def make_request():
            return limiter.is_allowed(key, max_requests=limit, window_seconds=10.0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(30)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        allowed_count = sum(1 for r in results if r is True)
        denied_count = sum(1 for r in results if r is False)

        assert allowed_count == limit, f"Expected exactly {limit} allowed requests, got {allowed_count}"
        assert denied_count == (30 - limit), f"Expected {30 - limit} denied requests, got {denied_count}"


# ===========================================================================
# 7. Deep Secret Scrubbing & Redaction Edge Cases
# ===========================================================================

class TestDeepSecretScrubbingAndRedaction:
    """Challenges the regex scrubbers with complex and obscure secret formats."""

    def test_scrub_secrets_mixed_case_private_key(self):
        leak = "Private key is 0x4F3EDF983AC636A65A842CE7C78D9AA706D3B113BCE9C46F30D7D21715B23B1D"
        scrubbed = scrub_secrets(leak)
        assert "4F3EDF983AC636A65A842CE7C78D9AA706D3B113BCE9C46F30D7D21715B23B1D" not in scrubbed
        assert "0x***REDACTED_PRIVATE_KEY***" in scrubbed

    def test_scrub_multiple_secrets_in_single_trace(self):
        leak = (
            "Failure: https://arb-mainnet.g.alchemy.com/v2/secret_alchemy_1 "
            "and https://arbitrum-mainnet.infura.io/v3/secret_infura_2 "
            "using key 0x1111111111111111111111111111111111111111111111111111111111111111"
        )
        scrubbed = scrub_secrets(leak)
        assert "secret_alchemy_1" not in scrubbed
        assert "secret_infura_2" not in scrubbed
        assert "1111111111111111111111111111111111111111111111111111111111111111" not in scrubbed
        assert "alchemy.com/v2/REDACTED" in scrubbed
        assert "infura.io/v3/REDACTED" in scrubbed
        assert "0x***REDACTED_PRIVATE_KEY***" in scrubbed

    def test_sanitize_secret_trace_empty_secrets_list(self):
        """Sanitizing with empty secrets list should not raise errors and preserves text."""
        msg = "Standard connection timeout after 3000ms"
        assert sanitize_secret_trace(msg, []) == msg
        assert sanitize_secret_trace(msg, [""]) == msg


# ===========================================================================
# 8. Non-ASCII Token Handling & Crash Resistance
# ===========================================================================

class TestNonAsciiTokenHandling:
    """Empirical challenge testing non-ASCII tokens in query parameters and WebSocket handshakes."""

    def test_non_ascii_query_token_handling(self, prod_client):
        """Testing whether non-ASCII tokens result in 401 Unauthorized or unhandled 500 TypeError."""
        try:
            res = prod_client.get("/events/reasoning?token=\U0001F511&limit=1")
            assert res.status_code == 401, f"Expected 401 Unauthorized for non-ASCII token, got {res.status_code}"
        except TypeError as e:
            pytest.fail(f"VULNERABILITY CONFIRMED: hmac.compare_digest crashed with TypeError on non-ASCII token: {e}")

    def test_non_ascii_websocket_token_handling(self, prod_client):
        """Testing whether non-ASCII tokens in WebSocket query params cleanly disconnect with 1008 or crash."""
        try:
            with prod_client.websocket_connect("/ws/telemetry?token=%F0%9F%94%91"):
                pytest.fail("WebSocket should have been rejected")
        except WebSocketDisconnect as ws_disc:
            assert ws_disc.code == 1008
        except TypeError as e:
            pytest.fail(f"VULNERABILITY CONFIRMED: WebSocket auth crashed with TypeError on non-ASCII token: {e}")


# ===========================================================================
# 9. Bridge Pending Transaction Exposure Challenge
# ===========================================================================

class TestBridgePendingTransactionExposure:
    """Empirical challenge testing unauthenticated transaction visibility on bridge."""

    def test_bridge_pending_transactions_unauthenticated_exposure(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_VALID_KEY)
        server = EIP1193BridgeServer()
        client = TestClient(server.app)

        server.stage_transaction_sync({"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 1000})
        res = client.get("/pending")
        if res.status_code == 200:
            pytest.fail(
                f"VULNERABILITY CONFIRMED: Unauthenticated access to /pending allowed in production! Staged transactions exposed: {res.json()}"
            )
        assert res.status_code == 401
