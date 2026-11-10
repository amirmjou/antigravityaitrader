"""
Adversarial Security Hardening Test Suite (Milestone 6: Features F27–F33).
Validates dual-mode authentication gateway, strict CORS, HTTP security headers,
rate limiting, keystore POSIX permissions, secret scrubbing, and container isolation.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.dataflows.net import scrub_secrets, sanitize_secret_trace
from crypto_pipeline.remote_agent.bridge import get_sanitized_subprocess_env
from execution.wallet.eip1193_bridge import EIP1193BridgeServer, create_bridge_app
from execution.wallet.hot_signer import HotKeystoreSigner
from visualization.server.app import create_visualization_app
from visualization.server.security import (
    global_rate_limiter,
    global_simulation_cache,
    is_auth_enforced,
    is_production_mode,
    verify_token_string,
)
from visualization.telemetry.hub import TelemetryHub

TEST_API_KEY = "test_super_secret_trading_api_key_m6_999"


@pytest.fixture(autouse=True)
def reset_security_state(monkeypatch):
    """Ensure clean environment, reset rate limits and caches for each test."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()


@pytest.fixture
def test_app():
    hub = TelemetryHub()
    return create_visualization_app(hub=hub)


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


# ===========================================================================
# 1. Dual-Mode Authentication & Auth Gateway (F27)
# ===========================================================================

class TestDualModeAuthentication:
    def test_dev_mode_without_key_allows_unauthenticated_requests(self, client):
        """In development mode with no API key, requests must pass through."""
        res_rpc = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1})
        assert res_rpc.status_code == 200
        assert res_rpc.json()["result"] == "0xa4b1"

        res_send = client.post("/send-transaction", json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 1000})
        assert res_send.status_code == 200

        res_confirm = client.post("/confirm-transaction", json={"request_id": res_send.json()["request_id"], "tx_hash": "0x1234"})
        assert res_confirm.status_code == 200

    def test_production_mode_blocks_unauthenticated_rpc(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1})
        assert res.status_code == 401
        assert res.json()["detail"] == "Unauthorized"

    def test_production_mode_blocks_unauthenticated_send_transaction(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.post("/send-transaction", json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 1000})
        assert res.status_code == 401

    def test_production_mode_blocks_unauthenticated_confirm_transaction(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.post("/confirm-transaction", json={"request_id": "nonexistent", "tx_hash": "0x1234"})
        assert res.status_code == 401

    def test_production_mode_blocks_unauthenticated_performance(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.get("/api/performance/100-trades")
        assert res.status_code == 401

    def test_production_mode_blocks_unauthenticated_sse(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.get("/events/reasoning?limit=1")
        assert res.status_code == 401

    def test_production_mode_blocks_unauthenticated_ws(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        with pytest.raises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws/telemetry"):
                pass

    def test_authenticated_requests_succeed_bearer(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 200
        assert res.json()["result"] == "0xa4b1"

    def test_authenticated_requests_succeed_x_api_key(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        headers = {"X-API-Key": TEST_API_KEY}
        res = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res.status_code == 200

    def test_authenticated_requests_succeed_query_param(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        # SSE query param
        res = client.get(f"/events/reasoning?token={TEST_API_KEY}&limit=1")
        assert res.status_code == 200

        # WS query param
        with client.websocket_connect(f"/ws/telemetry?token={TEST_API_KEY}") as ws:
            ws.send_json({"type": "ping", "timestamp": 12345})
            data = ws.receive_json()
            assert data["channel"] == "websocket"

    def test_health_endpoints_remain_public(self, monkeypatch, test_app):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res_h = client.get("/health")
        assert res_h.status_code == 200
        assert res_h.json()["status"] == "ok"

        res_api_h = client.get("/api/health")
        assert res_api_h.status_code == 200
        assert res_api_h.json()["status"] == "ok"

    def test_non_ascii_token_constant_time_comparison_safe(self, monkeypatch):
        """Regression test: verify non-ASCII tokens (emojis, Unicode, null bytes) safely return False without TypeError."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)

        # Constant-time comparison must not raise TypeError on non-ASCII characters
        assert verify_token_string("🔑") is False
        assert verify_token_string("密钥_token_123") is False
        assert verify_token_string("test\x00key") is False
        assert verify_token_string(None) is False
        assert verify_token_string("") is False
        assert verify_token_string(TEST_API_KEY) is True

    def test_production_mode_rejects_non_ascii_query_and_ws_tokens(self, monkeypatch, test_app):
        """Regression test: non-ASCII tokens in query strings and WS handshakes return HTTP 401 or close 1008."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)
        client = TestClient(test_app)

        res = client.get("/events/reasoning?token=🔑")
        assert res.status_code == 401

        res_perf = client.get("/api/performance/100-trades?token=🔑")
        assert res_perf.status_code == 401

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/telemetry?token=%F0%9F%94%91"):
                pass
        assert excinfo.value.code == 1008


# ===========================================================================
# 2. Bridge Authentication Hardening
# ===========================================================================

class TestBridgeAuthentication:
    def test_bridge_endpoints_require_auth_in_production(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)

        bridge_server = EIP1193BridgeServer()
        client = TestClient(bridge_server.app)

        # Unauthenticated calls should be rejected
        res = client.post("/send-transaction", json={"to": "0x1111111111111111111111111111111111111111", "amount_in_wei": 500})
        assert res.status_code == 401

        res_rpc = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_accounts", "id": 1})
        assert res_rpc.status_code == 401

        with pytest.raises((WebSocketDisconnect, Exception)):
            with client.websocket_connect("/ws"):
                pass

        # Authenticated calls succeed
        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        res_auth = client.post("/rpc", json={"jsonrpc": "2.0", "method": "eth_chainId", "id": 1}, headers=headers)
        assert res_auth.status_code == 200

    def test_bridge_pending_and_request_accounts_require_auth_in_production(self, monkeypatch):
        """Regression test: /pending and /request-accounts must require auth in production mode."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", TEST_API_KEY)

        bridge_server = EIP1193BridgeServer()
        client = TestClient(bridge_server.app)

        bridge_server.stage_transaction_sync({
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in_wei": 1000,
        })

        # Unauthenticated access to /pending must return 401
        res_pending_unauth = client.get("/pending")
        assert res_pending_unauth.status_code == 401

        # Unauthenticated access to /request-accounts must return 401
        res_req_acc_get = client.get("/request-accounts")
        assert res_req_acc_get.status_code == 401

        res_req_acc_post = client.post("/request-accounts")
        assert res_req_acc_post.status_code == 401

        # Authenticated access succeeds
        headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
        res_pending_auth = client.get("/pending", headers=headers)
        assert res_pending_auth.status_code == 200
        assert len(res_pending_auth.json()["pending"]) >= 1

        res_accounts_auth = client.get("/request-accounts", headers=headers)
        assert res_accounts_auth.status_code == 200
        assert "accounts" in res_accounts_auth.json()


# ===========================================================================
# 3. HTTP Security Headers & Strict CORS (F28)
# ===========================================================================

class TestSecurityHeadersAndCORS:
    def test_all_responses_contain_security_headers(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert "max-age=31536000" in res.headers.get("strict-transport-security", "")
        assert "default-src 'self'" in res.headers.get("content-security-policy", "")
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_cors_rejects_untrusted_origins_in_production(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://trading.mycloud.com,http://localhost:3000")
        app = create_visualization_app()
        client = TestClient(app)

        # Untrusted origin
        res = client.options(
            "/health",
            headers={"Origin": "https://malicious-hacker.com", "Access-Control-Request-Method": "GET"},
        )
        assert res.headers.get("access-control-allow-origin") != "https://malicious-hacker.com"
        assert res.headers.get("access-control-allow-origin") != "*"

    def test_cors_allows_trusted_origins_in_production(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://trading.mycloud.com,http://localhost:3000")
        app = create_visualization_app()
        client = TestClient(app)

        res = client.options(
            "/health",
            headers={"Origin": "https://trading.mycloud.com", "Access-Control-Request-Method": "GET"},
        )
        assert res.headers.get("access-control-allow-origin") == "https://trading.mycloud.com"


# ===========================================================================
# 4. Rate Limiting & DoS Defense (F29)
# ===========================================================================

class TestRateLimitingAndCaching:
    def test_rate_limiter_blocks_excessive_simulation_requests(self, client):
        """Simulation endpoints allow max 5 requests per minute."""
        for _ in range(5):
            res = client.get("/api/performance/100-trades")
            assert res.status_code == 200

        # 6th request within window must be rate limited with HTTP 429
        res_limit = client.get("/api/performance/100-trades")
        assert res_limit.status_code == 429
        assert res_limit.json()["detail"] == "Too Many Requests"

    def test_simulation_caching_prevents_repeated_execution(self, client):
        """Verify simulation caching stores result and reuses it."""
        res1 = client.get("/api/performance/100-trades?initial_capital=50.0&trades=10")
        assert res1.status_code == 200

        # Cached result returned immediately
        res2 = client.get("/api/performance/100-trades?initial_capital=50.0&trades=10")
        assert res2.status_code == 200
        assert res1.json() == res2.json()


# ===========================================================================
# 5. Keystore POSIX Permissions & Masked Private Key (F30)
# ===========================================================================

class TestKeystoreHardening:
    def test_keystore_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "test_keystore.json"
            signer = HotKeystoreSigner.create_new()
            saved_path = signer.save_keystore_file(key_path, "password123")
            assert saved_path.exists()

            # Verify file permissions
            file_mode = stat.S_IMODE(os.stat(saved_path).st_mode)
            # On POSIX, exactly 0600 (owner read/write only). On Windows, check read/write works.
            if os.name == "posix":
                assert file_mode == 0o600

    def test_hot_keystore_signer_repr_and_str_mask_private_key(self):
        raw_key = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
        signer = HotKeystoreSigner.from_private_key(raw_key)

        repr_str = repr(signer)
        str_str = str(signer)

        # Raw private key must never appear in repr or str
        assert raw_key not in repr_str
        assert raw_key not in str_str

        # Masked representation should be present
        assert "0x4f3e...3b1d" in repr_str
        assert signer.address in repr_str
        assert signer.address in str_str


# ===========================================================================
# 6. Secret Scrubbing & Trace Redaction (F30)
# ===========================================================================

class TestSecretScrubbing:
    def test_scrub_secrets_masks_alchemy_urls(self):
        leak = "Error connecting to https://arb-mainnet.g.alchemy.com/v2/my_secret_token_12345 during block fetch"
        scrubbed = scrub_secrets(leak)
        assert "my_secret_token_12345" not in scrubbed
        assert "https://arb-mainnet.g.alchemy.com/v2/REDACTED" in scrubbed

    def test_scrub_secrets_masks_infura_urls(self):
        leak = "Infura request failed: https://arbitrum-mainnet.infura.io/v3/infura_token_9999"
        scrubbed = scrub_secrets(leak)
        assert "infura_token_9999" not in scrubbed
        assert "https://arbitrum-mainnet.infura.io/v3/REDACTED" in scrubbed

    def test_scrub_secrets_masks_private_keys(self):
        leak = "Signer failed with 0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d on chain 42161"
        scrubbed = scrub_secrets(leak)
        assert "4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d" not in scrubbed
        assert "0x***REDACTED_PRIVATE_KEY***" in scrubbed

    def test_scrub_secrets_masks_bearer_tokens(self):
        leak = "Header authorization was Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
        scrubbed = scrub_secrets(leak)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token" not in scrubbed
        assert "Bearer REDACTED" in scrubbed

    def test_sanitize_secret_trace_masks_explicit_secrets(self):
        raw_trace = "Exception connecting to node with key secret_passphrase_xyz123!"
        sanitized = sanitize_secret_trace(raw_trace, secrets=["secret_passphrase_xyz123!"])
        assert "secret_passphrase_xyz123!" not in sanitized
        assert "***REDACTED***" in sanitized


# ===========================================================================
# 7. Subprocess Environment Whitelisting (F30)
# ===========================================================================

class TestSubprocessEnvironmentWhitelisting:
    def test_remote_agent_bridge_subprocess_env_whitelist(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-super-secret-key-12345")
        monkeypatch.setenv("TRADING_API_KEY", "trading-api-key-999")
        monkeypatch.setenv("ETH_PRIVATE_KEY", "0x1234567890abcdef")
        monkeypatch.setenv("AGY_CUSTOM_PARAM", "custom_param_value")

        safe_env = get_sanitized_subprocess_env()

        # Sensitive keys must be scrubbed out of child environment
        assert "OPENAI_API_KEY" not in safe_env
        assert "TRADING_API_KEY" not in safe_env
        assert "ETH_PRIVATE_KEY" not in safe_env

        # Whitelisted prefix should remain
        assert safe_env.get("AGY_CUSTOM_PARAM") == "custom_param_value"


# ===========================================================================
# 8. Container & Deployment Hardening (F31)
# ===========================================================================

class TestContainerDeploymentHardening:
    def test_dockerfile_security_attributes(self):
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile must exist at repository root"
        content = dockerfile_path.read_text(encoding="utf-8")

        # Multi-stage check
        assert "AS builder" in content
        assert "AS runner" in content

        # Non-root UID 10001
        assert "USER 10001:10001" in content
        assert "groupadd -g 10001" in content
        assert "useradd -u 10001" in content

        # Read-only code ownership and 700 isolated state
        assert "chmod 700 /app/keystores /app/data" in content
        assert "HEALTHCHECK" in content

    def test_docker_compose_security_attributes(self):
        compose_path = Path("docker-compose.prod.yml")
        assert compose_path.exists(), "docker-compose.prod.yml must exist at repository root"
        content = compose_path.read_text(encoding="utf-8")

        assert "read_only: true" in content
        assert "no-new-privileges:true" in content
        assert "cap_drop:" in content
        assert "- ALL" in content
        assert 'user: "10001:10001"' in content
        assert "internal_net" in content

    def test_caddyfile_configuration(self):
        caddy_path = Path("deploy/Caddyfile")
        assert caddy_path.exists(), "deploy/Caddyfile must exist"
        content = caddy_path.read_text(encoding="utf-8")

        assert "reverse_proxy trading-server:8899" in content
        assert "X-Frame-Options \"DENY\"" in content
        assert "Strict-Transport-Security" in content

    def test_gitignore_protects_secrets_and_keystores(self):
        gitignore_path = Path(".gitignore")
        assert gitignore_path.exists(), ".gitignore must exist"
        content = gitignore_path.read_text(encoding="utf-8")

        assert ".env" in content
        assert "keystores/" in content
        assert "secrets/" in content
        assert "*.key" in content
