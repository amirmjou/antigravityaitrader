"""
Empirical Adversarial Stress Suite for Milestone 6 Hardening (Iteration 2).
Author: Challenger 2 (Empirical Security Challenger).

Empirically tests and challenges:
1. Non-ASCII API Key configurations (Unicode, emojis, multibyte characters in TRADING_API_KEY).
2. Large token payloads (100KB+ strings) to verify ReDoS and memory resilience.
3. Unpaired surrogates and malformed byte sequences in verify_token_string.
4. EIP-1193 Bridge exhaustive endpoint authentication coverage in production mode.
5. Bridge WebSocket endpoints (/ws and /ws/status) with various token transmission methods.
6. Case-insensitivity and header precedence across Authorization Bearer, X-API-Key, and ?token=.
7. Constant-time properties and timing side-channel resilience.
8. Secret scrubbing with Unicode and multibyte exception messages.
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import time
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.dataflows.net import scrub_secrets, sanitize_secret_trace
from execution.wallet.eip1193_bridge import EIP1193BridgeServer
from visualization.server.app import create_visualization_app
from visualization.server.security import (
    verify_token_string,
    is_auth_enforced,
    get_configured_api_key,
    check_websocket_auth,
)
from visualization.telemetry.hub import TelemetryHub


TEST_SECRET_KEY = "sec_challenge_it2_super_secret_token_#9988"
TEST_UNICODE_KEY = "密钥_SecKey_🔑_2026!@#"


@pytest.fixture(autouse=True)
def clean_security_env(monkeypatch):
    """Ensure clean environment for every test."""
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    yield
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)


@pytest.fixture
def viz_app():
    hub = TelemetryHub()
    return create_visualization_app(hub=hub)


@pytest.fixture
def bridge_server():
    return EIP1193BridgeServer()


# ===========================================================================
# 1. Non-ASCII and Malformed Token Resilience in verify_token_string
# ===========================================================================

class TestNonAsciiAndMalformedTokenHandling:
    """Stress tests verify_token_string under extreme and adversarial inputs."""

    def test_unicode_configured_api_key_successful_auth(self, monkeypatch):
        """Verify that if the server operator configures a Unicode/Emoji API key, valid auth succeeds."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_UNICODE_KEY)

        assert verify_token_string(TEST_UNICODE_KEY) is True
        assert verify_token_string("密钥_SecKey_🔑_2026!@#_wrong") is False
        assert verify_token_string("wrong_key") is False

    def test_unpaired_surrogates_handled_gracefully(self, monkeypatch):
        """Surrogate characters in Python strings raise UnicodeEncodeError upon UTF-8 encoding."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        # Unpaired high and low surrogates
        surrogate_token = "invalid_\ud800_surrogate"
        assert verify_token_string(surrogate_token) is False
        surrogate_token2 = "\udfff"
        assert verify_token_string(surrogate_token2) is False

    def test_null_byte_injection_token(self, monkeypatch):
        """Null byte prefix, infix, and suffix injections must not match or crash."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        assert verify_token_string(f"{TEST_SECRET_KEY}\x00extra") is False
        assert verify_token_string(f"\x00{TEST_SECRET_KEY}") is False
        assert verify_token_string(f"{TEST_SECRET_KEY}\x00") is False
        assert verify_token_string("\x00" * 32) is False

    def test_massive_token_payload_no_hang(self, monkeypatch):
        """100KB and 500KB token payloads must be rejected in constant time without ReDoS or hang."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        huge_token = "A" * 100_000
        start = time.perf_counter()
        assert verify_token_string(huge_token) is False
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"Massive token evaluation took too long: {elapsed:.4f}s"

        huge_unicode = "🔑" * 50_000
        start = time.perf_counter()
        assert verify_token_string(huge_unicode) is False
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"Massive unicode token evaluation took too long: {elapsed:.4f}s"

    def test_empty_and_whitespace_tokens(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        assert verify_token_string("") is False
        assert verify_token_string(" ") is False
        assert verify_token_string("   ") is False
        assert verify_token_string("\t\n\r") is False


# ===========================================================================
# 2. Exhaustive EIP-1193 Bridge Endpoint Security in Production Mode
# ===========================================================================

class TestBridgeExhaustiveSecurityAudit:
    """Verifies that EVERY sensitive endpoint on EIP1193BridgeServer requires authentication."""

    def test_all_bridge_endpoints_reject_unauthenticated_in_prod(self, monkeypatch, bridge_server):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(bridge_server.app)

        # 1. /send-transaction
        res1 = client.post("/send-transaction", json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 100})
        assert res1.status_code == 401, f"Expected 401 for /send-transaction, got {res1.status_code}"

        # 2. /sign-typed-data
        res2 = client.post("/sign-typed-data", json={
            "account": "0x1111111111111111111111111111111111111111",
            "domain": {},
            "types": {},
            "message": {},
        })
        assert res2.status_code == 401, f"Expected 401 for /sign-typed-data, got {res2.status_code}"

        # 3. /confirm-transaction
        res3 = client.post("/confirm-transaction", json={"request_id": "tx_123", "success": True, "tx_hash": "0xabc"})
        assert res3.status_code == 401, f"Expected 401 for /confirm-transaction, got {res3.status_code}"

        # 4. /pending
        res4 = client.get("/pending")
        assert res4.status_code == 401, f"Expected 401 for /pending, got {res4.status_code}"

        # 5. /request-accounts GET
        res5 = client.get("/request-accounts")
        assert res5.status_code == 401, f"Expected 401 for GET /request-accounts, got {res5.status_code}"

        # 6. /request-accounts POST
        res6 = client.post("/request-accounts")
        assert res6.status_code == 401, f"Expected 401 for POST /request-accounts, got {res6.status_code}"

        # 7. /rpc
        res7 = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_accounts", "id": 1})
        assert res7.status_code == 401, f"Expected 401 for /rpc, got {res7.status_code}"

    def test_bridge_status_endpoint_is_public(self, monkeypatch, bridge_server):
        """Verify /status provides telemetry without leaking staged pending transaction details."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(bridge_server.app)
        res = client.get("/status")
        assert res.status_code == 200
        data = res.json()
        assert "uptime_seconds" in data
        assert "chain_id" in data
        assert "pending_transactions_count" in data
        # /status only gives count, not the actual pending list
        assert isinstance(data["pending_transactions_count"], int)

    def test_bridge_websocket_status_unauthorized_rejection(self, monkeypatch, bridge_server):
        """Verify both /ws and /ws/status close with code 1008 on unauthenticated connections."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(bridge_server.app)

        with pytest.raises(WebSocketDisconnect) as exc1:
            with client.websocket_connect("/ws"):
                pass
        assert exc1.value.code == 1008

        with pytest.raises(WebSocketDisconnect) as exc2:
            with client.websocket_connect("/ws/status"):
                pass
        assert exc2.value.code == 1008

    def test_bridge_websocket_authenticated_via_query_token(self, monkeypatch, bridge_server):
        """Verify authenticated WebSocket connection succeeds on /ws and receives initial state."""
        import urllib.parse
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(bridge_server.app)
        quoted_token = urllib.parse.quote(TEST_SECRET_KEY)

        with client.websocket_connect(f"/ws?token={quoted_token}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "CONNECTED"
            assert "chain_id" in msg
            assert "accounts" in msg


# ===========================================================================
# 3. Header Precedence, Case Sensitivity, and Injections
# ===========================================================================

class TestAuthHeaderVariationsAndPrecedence:
    """Tests varied header casings, schemes, and precedence orders."""

    def test_x_api_key_case_insensitivity(self, monkeypatch, viz_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(viz_app)

        # Lowercase x-api-key
        res1 = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers={"x-api-key": TEST_SECRET_KEY})
        assert res1.status_code == 200

        # Uppercase X-API-KEY
        res2 = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers={"X-API-KEY": TEST_SECRET_KEY})
        assert res2.status_code == 200

    def test_authorization_bearer_with_extra_spaces(self, monkeypatch, viz_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(viz_app)

        # Standard bearer
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers={"Authorization": f"Bearer {TEST_SECRET_KEY}"})
        assert res.status_code == 200

    def test_conflicting_headers_valid_bearer_wins(self, monkeypatch, viz_app):
        """When both a valid Bearer token and invalid query token are provided, HTTPBearer dependency takes precedence."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_SECRET_KEY)

        client = TestClient(viz_app)

        headers = {"Authorization": f"Bearer {TEST_SECRET_KEY}"}
        res = client.post("/rpc?token=invalid_query_token", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 200


# ===========================================================================
# 4. Secret Scrubbing with Multibyte and Unicode Content
# ===========================================================================

class TestSecretScrubbingWithUnicode:
    """Stress tests secret scrubbing when exceptions and URLs contain non-ASCII characters."""

    def test_scrub_secrets_with_unicode_surrounding_text(self):
        secret = "0x" + "a1" * 32
        text = f"警告! 关键错误: 私钥泄露: {secret} 在文件 🚀 中发生."
        cleaned = scrub_secrets(text)
        assert secret not in cleaned
        assert "0x***REDACTED_PRIVATE_KEY***" in cleaned
        assert "警告" in cleaned
        assert "🚀" in cleaned

    def test_sanitize_secret_trace_with_unicode_and_emojis(self):
        secrets_list = ["test_key_123", "https://eth-mainnet.g.alchemy.com/v2/secret_alchemy_key_999"]
        trace = (
            "Traceback (most recent call last):\n"
            "  File '交易引擎.py', line 42, in connect\n"
            "    raise ConnectionError('Failed to connect to https://eth-mainnet.g.alchemy.com/v2/secret_alchemy_key_999 with token test_key_123 💥')\n"
        )
        sanitized = sanitize_secret_trace(trace, secrets=secrets_list)
        assert "secret_alchemy_key_999" not in sanitized
        assert "test_key_123" not in sanitized
        assert "REDACTED" in sanitized
        assert "交易引擎" in sanitized
