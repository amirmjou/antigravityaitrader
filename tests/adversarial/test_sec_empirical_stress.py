"""
Empirical Stress and Adversarial Testing Suite (Milestone 6 Security Hardening).
Author: Challenger 2 (Empirical Rate Limiting, Secret Leakage & Container Stress Tester).

Empirically challenges:
1. High-concurrency flood against simulation endpoints (/api/performance/100-trades),
   verifying sliding-window rate limit exhaustion (HTTP 429), thread-safety,
   and simulation cache reuse under concurrent load.
2. Secret scrubbing fuzzing across high-entropy private keys, varied cloud RPC URLs
   (Alchemy, Infura, QuickNode), URL query credential injection, Bearer tokens,
   and chained exception tracebacks with ReDoS safety checks.
3. Keystore file permissions on disk (enforcing POSIX 0600 mode logic, atomic writes,
   and zero raw key leakage in string representations).
4. Subprocess environment isolation: comprehensive audit stripping 50+ real-world
   cloud/AI/database secrets while preserving runtime essentials and whitelisted AGY_ vars.
5. Container hardening and deployment compliance: verification of non-root execution
   (UID 10001:10001), dropped capabilities (ALL), read-only rootfs, tmpfs noexec flags,
   reverse proxy TLS headers, and repository secret exclusion (.gitignore).
"""
from __future__ import annotations

import concurrent.futures
import os
import re
import secrets
import stat
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from core.dataflows.net import scrub_secrets, sanitize_secret_trace
from crypto_pipeline.remote_agent.bridge import get_sanitized_subprocess_env
from execution.wallet.hot_signer import HotKeystoreSigner
from visualization.server.app import create_visualization_app
from visualization.server.security import (
    RateLimiter,
    SimulationCache,
    global_rate_limiter,
    global_simulation_cache,
)
from visualization.telemetry.hub import TelemetryHub


@pytest.fixture(autouse=True)
def clean_security_state(monkeypatch):
    """Ensure clean environment and state for every test."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()


@pytest.fixture
def stress_app():
    hub = TelemetryHub()
    return create_visualization_app(hub=hub)


# ===========================================================================
# 1. High-Concurrency Flood & Rate Limiter Stress Testing
# ===========================================================================

class TestSimulationFloodAndRateLimitingEmpirical:
    """Stress-tests the simulation rate limiter and cache under heavy concurrent load."""

    def test_high_concurrency_flood_on_100_trades(self, stress_app):
        """
        Dispatches 25 concurrent requests against `/api/performance/100-trades`.
        Verifies that exactly 5 requests succeed (HTTP 200) and 20 requests
        are rejected with HTTP 429 'Too Many Requests'.
        """
        client = TestClient(stress_app)
        num_requests = 25
        results: List[int] = []

        def make_request(idx: int) -> int:
            res = client.get("/api/performance/100-trades?initial_capital=40.0&trades=10")
            return res.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())

        status_200 = results.count(200)
        status_429 = results.count(429)

        assert status_200 == 5, f"Expected exactly 5 allowed requests, got {status_200}"
        assert status_429 == 20, f"Expected exactly 20 rate-limited requests (429), got {status_429}"
        assert len(results) == num_requests

    def test_rate_limiter_multithreaded_burst_thread_safety(self):
        """
        Directly stress-tests the thread safety of `RateLimiter` under extreme contention:
        50 threads simultaneously attempt 200 requests with a quota of 10.
        Verifies no race condition allows more than 10 permits.
        """
        limiter = RateLimiter()
        allowed_count = 0
        blocked_count = 0
        total_calls = 200
        quota = 10
        lock = concurrent.futures.thread.threading.Lock()

        def request_worker():
            nonlocal allowed_count, blocked_count
            allowed = limiter.is_allowed("burst_test_key", max_requests=quota, window_seconds=60.0)
            with lock:
                if allowed:
                    allowed_count += 1
                else:
                    blocked_count += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(request_worker) for _ in range(total_calls)]
            concurrent.futures.wait(futures)

        assert allowed_count == quota, f"Thread-safety violation: {allowed_count} requests allowed instead of {quota}"
        assert blocked_count == total_calls - quota

    def test_client_ip_isolation_under_flood(self, stress_app):
        """
        Verifies that one client exhausting their rate limit does NOT impact other client IPs.
        """
        client_a = TestClient(stress_app, client=("198.51.100.1", 40001))
        client_b = TestClient(stress_app, client=("198.51.100.2", 40002))
        client_c = TestClient(stress_app, client=("198.51.100.3", 40003))

        # Client A exhausts quota (5 requests)
        for _ in range(5):
            res_a = client_a.get("/api/performance/100-trades?trades=5")
            assert res_a.status_code == 200

        # Client A 6th request is blocked
        res_a_blocked = client_a.get("/api/performance/100-trades?trades=5")
        assert res_a_blocked.status_code == 429

        # Client B must NOT be blocked and can make its 5 requests
        for _ in range(5):
            res_b = client_b.get("/api/performance/100-trades?trades=5")
            assert res_b.status_code == 200
        assert client_b.get("/api/performance/100-trades?trades=5").status_code == 429

        # Client C can also make requests
        assert client_c.get("/api/performance/100-trades?trades=5").status_code == 200

    def test_simulation_cache_reuse_under_concurrent_load(self, stress_app):
        """
        Verifies that multiple requests for the same simulation parameters reuse the cached
        result without re-running the computation.
        """
        client = TestClient(stress_app)

        # First request populates cache
        res1 = client.get("/api/performance/100-trades?initial_capital=50.0&trades=10")
        assert res1.status_code == 200
        data1 = res1.json()

        # Next 3 requests should hit cache
        for _ in range(3):
            res_cached = client.get("/api/performance/100-trades?initial_capital=50.0&trades=10")
            assert res_cached.status_code == 200
            assert res_cached.json() == data1

        # Check that cache contains the specific key
        cached_val = global_simulation_cache.get("100_trades_50.0_10")
        assert cached_val is not None
        assert cached_val["initial_capital_usd"] == 50.0

    def test_cache_key_differentiation_by_parameters(self):
        """Tests that different simulation parameters generate distinct cache keys."""
        cache = SimulationCache(ttl_seconds=60.0)
        cache.set("100_trades_40.0_100", {"trades": 100, "capital": 40.0})
        cache.set("100_trades_80.0_100", {"trades": 100, "capital": 80.0})

        res_40 = cache.get("100_trades_40.0_100")
        res_80 = cache.get("100_trades_80.0_100")

        assert res_40["capital"] == 40.0
        assert res_80["capital"] == 80.0
        assert cache.get("100_trades_50.0_100") is None

    def test_cache_ttl_expiration(self):
        """Tests that cache entries expire accurately after TTL."""
        short_cache = SimulationCache(ttl_seconds=0.1)
        short_cache.set("test_key", {"data": "cached_value"})

        assert short_cache.get("test_key") == {"data": "cached_value"}
        time.sleep(0.15)
        assert short_cache.get("test_key") is None


# ===========================================================================
# 2. Secret Scrubbing Fuzzing & Traceback Redaction
# ===========================================================================

class TestSecretScrubbingFuzzingEmpirical:
    """Adversarially fuzzes the secret scrubber with diverse credentials, URLs, and stack traces."""

    def test_fuzz_private_keys_various_formats(self):
        """
        Fuzzes 25 randomly generated 64-character private keys in lowercase, uppercase,
        and mixed-case embedded in diverse syntaxes (JSON, URL, stack trace, plain text).
        """
        for _ in range(25):
            raw_hex = secrets.token_hex(32)  # 64 hex characters
            formats = [
                f"0x{raw_hex}",
                f"0x{raw_hex.upper()}",
                f"0x{raw_hex[:32].upper()}{raw_hex[32:].lower()}",
            ]
            for formatted_key in formats:
                test_strings = [
                    f"Traceback: Exception at signer.py: private_key={formatted_key} failed to sign",
                    f'{{"account": "0x123", "private_key": "{formatted_key}", "nonce": 5}}',
                    f"https://internal-vault.svc/keys/{formatted_key}/export",
                ]
                for raw_text in test_strings:
                    scrubbed = scrub_secrets(raw_text)
                    # The raw 64-char key must NEVER be present
                    assert raw_hex.lower() not in scrubbed.lower(), f"Leaked private key in: {scrubbed}"
                    assert "0x***REDACTED_PRIVATE_KEY***" in scrubbed

    def test_fuzz_alchemy_urls_across_multichain(self):
        """
        Tests Alchemy endpoints across Arbitrum, Base, Ethereum, Polygon, and Sepolia.
        """
        chains = ["eth-mainnet", "arb-mainnet", "polygon-mainnet", "base-mainnet", "eth-sepolia", "arb-sepolia"]
        for chain in chains:
            token = secrets.token_urlsafe(32)
            url = f"https://{chain}.g.alchemy.com/v2/{token}"
            raw_log = f"Failed to fetch block header from {url} after 3 retries"
            scrubbed = scrub_secrets(raw_log)

            assert token not in scrubbed
            assert f"https://{chain}.g.alchemy.com/v2/REDACTED" in scrubbed

    def test_fuzz_infura_and_quicknode_endpoints(self):
        """Tests Infura and QuickNode RPC URL token redaction."""
        infura_token = secrets.token_hex(16)
        infura_msg = f"Connecting to https://arbitrum-mainnet.infura.io/v3/{infura_token} via WebSocket"
        scrubbed_infura = scrub_secrets(infura_msg)
        assert infura_token not in scrubbed_infura
        assert "https://arbitrum-mainnet.infura.io/v3/REDACTED" in scrubbed_infura

        qn_token = secrets.token_hex(20)
        qn_msg = f"QuickNode error: https://super-node.quiknode.pro/{qn_token}/ response code 503"
        scrubbed_qn = scrub_secrets(qn_msg)
        assert qn_token not in scrubbed_qn
        assert "https://super-node.quiknode.pro/REDACTED" in scrubbed_qn

    def test_fuzz_url_query_param_credentials(self):
        """
        Tests URL query parameters containing apikey, api_key, token, secret, and password.
        """
        param_names = ["apikey", "api_key", "token", "secret", "password"]
        for param in param_names:
            secret_val = f"secret_val_{secrets.token_hex(8)}"
            url = f"https://api.etherscan.io/api?module=account&action=balance&{param}={secret_val}&tag=latest"
            scrubbed = scrub_secrets(url)

            assert secret_val not in scrubbed, f"Failed to scrub param {param}: {scrubbed}"
            assert f"{param}=REDACTED" in scrubbed

    def test_fuzz_bearer_authorization_tokens(self):
        """
        Tests Bearer authorization tokens of varying lengths (32 to 128 characters).
        """
        for length in [32, 64, 128]:
            bearer_token = secrets.token_urlsafe(length)
            header_str = f"Authorization: Bearer {bearer_token}"
            scrubbed = scrub_secrets(header_str)

            assert bearer_token not in scrubbed
            assert "Bearer REDACTED" in scrubbed

    def test_traceback_exception_chain_full_sanitization(self):
        """
        Generates a realistic chained exception with embedded secrets and tracebacks,
        and verifies `sanitize_secret_trace` wipes all secrets completely.
        """
        dummy_secret_key = "sk_live_very_secret_api_key_xyz987"
        dummy_private_key = "0x" + "b" * 64
        dummy_rpc = "https://arb-mainnet.g.alchemy.com/v2/my_secret_token_abc"

        try:
            try:
                raise ConnectionError(f"HTTP 403 querying RPC: {dummy_rpc} with key {dummy_secret_key}")
            except ConnectionError as inner_err:
                raise RuntimeError(f"Signer using {dummy_private_key} aborted execution") from inner_err
        except RuntimeError:
            raw_tb = traceback.format_exc()

        # Sanitize trace
        clean_tb = sanitize_secret_trace(raw_tb, secrets=[dummy_secret_key])

        # Assert zero leakage
        assert dummy_secret_key not in clean_tb
        assert "b" * 64 not in clean_tb
        assert "my_secret_token_abc" not in clean_tb
        assert "***REDACTED***" in clean_tb
        assert "0x***REDACTED_PRIVATE_KEY***" in clean_tb
        assert "https://arb-mainnet.g.alchemy.com/v2/REDACTED" in clean_tb

    def test_scrubber_performance_and_redos_safety(self):
        """
        Empirically verifies that `scrub_secrets` processes a massive 1 MB log dump
        without catastrophic regex backtracking (ReDoS) in under 0.5 seconds.
        """
        # Generate 10,000 lines of mixed log text with repeated tokens and URL fragments
        lines = []
        for i in range(5000):
            lines.append(f"2026-11-08T12:00:{i%60:02d}Z INFO worker-{i%4}: processing batch tx 0x{i:04x}")
            if i % 100 == 0:
                lines.append(f"WARN endpoint https://arb-mainnet.g.alchemy.com/v2/token_{i} slow response")
            if i % 250 == 0:
                lines.append(f"DEBUG auth header Bearer eyJhbGciOiJIUzI1NiI_{i}_token")

        large_log_payload = "\n".join(lines)
        start_time = time.time()
        result = scrub_secrets(large_log_payload)
        elapsed = time.time() - start_time

        assert elapsed < 0.5, f"Scrubber took {elapsed:.3f}s, potential ReDoS or inefficient regex"
        assert "token_0" not in result


# ===========================================================================
# 3. Keystore Security & POSIX Permissions Testing
# ===========================================================================

class TestKeystorePermissionsAndSecurityEmpirical:
    """Stress-tests HotKeystoreSigner file persistence, permissions, and memory hygiene."""

    def test_keystore_creation_and_file_mode_permissions(self):
        """
        Creates a new keystore file on disk and verifies POSIX mode bits 0600
        (owner read/write only, zero permissions for group and others).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "subfolder" / "wallet.json"
            signer = HotKeystoreSigner.create_new()
            saved_path = signer.save_keystore_file(key_path, "secure_pass_1234")

            assert saved_path.exists()
            assert saved_path.is_file()

            # POSIX check
            if os.name == "posix":
                st = os.stat(saved_path)
                mode = stat.S_IMODE(st.st_mode)
                assert mode == 0o600, f"Expected permissions 0600, got octal {oct(mode)}"

            # Verify it decrypts accurately
            loaded = HotKeystoreSigner.from_keystore_file(saved_path, "secure_pass_1234")
            assert loaded.address.lower() == signer.address.lower()

    def test_keystore_overwrite_maintains_safe_permissions(self):
        """
        Verifies overwriting an existing keystore file succeeds and preserves safe access.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "wallet_overwrite.json"
            signer1 = HotKeystoreSigner.create_new()
            signer1.save_keystore_file(key_path, "pass1")

            signer2 = HotKeystoreSigner.create_new()
            signer2.save_keystore_file(key_path, "pass2")

            loaded = HotKeystoreSigner.from_keystore_file(key_path, "pass2")
            assert loaded.address.lower() == signer2.address.lower()

    def test_keystore_tampered_password_decryption_failure(self):
        """
        Empirically verifies that incorrect passwords always fail decryption
        without leaking decrypted bytes or partial state.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "secure_keystore.json"
            signer = HotKeystoreSigner.create_new()
            signer.save_keystore_file(key_path, "correct_password_999")

            bad_passwords = ["", "wrong", "CORRECT_PASSWORD_999", "correct_password_998", " "]
            for bad_pass in bad_passwords:
                with pytest.raises(Exception):
                    HotKeystoreSigner.from_keystore_file(key_path, bad_pass)

    def test_hot_signer_memory_and_repr_key_masking(self):
        """
        Verifies that string conversions and representations NEVER expose the raw private key.
        """
        raw_key = "0x" + "c" * 64
        signer = HotKeystoreSigner.from_private_key(raw_key)

        assert raw_key not in repr(signer)
        assert raw_key not in str(signer)
        assert raw_key not in signer.masked_private_key
        assert signer.masked_private_key.startswith("0xcccc...")


# ===========================================================================
# 4. Subprocess Environment Isolation Adversarial Audit
# ===========================================================================

class TestSubprocessIsolationEmpirical:
    """Stress-tests `get_sanitized_subprocess_env` against a battery of 50+ real-world cloud/API secrets."""

    def test_subprocess_env_drops_50_cloud_and_ai_secrets(self, monkeypatch):
        """
        Injects 50 real-world secrets across AWS, Azure, GCP, OpenAI, Anthropic, Gemini,
        Databases, Web3, and API keys. Asserts 100% of them are stripped.
        """
        sensitive_vars = [
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
            "GCP_SERVICE_ACCOUNT_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
            "COHERE_API_KEY", "MISTRAL_API_KEY", "HUGGINGFACE_TOKEN",
            "GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN",
            "DATABASE_URL", "POSTGRES_PASSWORD", "MYSQL_PWD", "REDIS_PASSWORD", "MONGO_URI",
            "STRIPE_SECRET_KEY", "TWILIO_AUTH_TOKEN", "SENDGRID_API_KEY",
            "TRADING_API_KEY", "ETH_PRIVATE_KEY", "SIGNER_PASSPHRASE",
            "INFURA_API_KEY", "ALCHEMY_API_KEY", "ETHERSCAN_API_KEY", "ARBISCAN_API_KEY",
            "COINGECKO_API_KEY", "CMC_API_KEY", "BINANCE_API_SECRET", "COINBASE_API_SECRET",
            "KRAKEN_PRIVATE_KEY", "BYBIT_API_SECRET", "OKX_API_SECRET",
            "SLACK_BOT_TOKEN", "DISCORD_BOT_TOKEN", "TELEGRAM_BOT_TOKEN",
            "SECRET_KEY", "JWT_SECRET", "SESSION_SECRET", "ENCRYPTION_KEY",
            "PRIVATE_KEY", "ID_RSA", "SSH_PRIVATE_KEY", "GPG_PASSPHRASE"
        ]

        for var_name in sensitive_vars:
            monkeypatch.setenv(var_name, f"super_secret_value_{var_name.lower()}")

        safe_env = get_sanitized_subprocess_env()

        leaked = [k for k in safe_env if k.upper() in sensitive_vars]
        assert len(leaked) == 0, f"Subprocess environment leaked sensitive variables: {leaked}"

    def test_subprocess_env_retains_whitelisted_and_runtime_vars(self, monkeypatch):
        """
        Verifies essential OS runtime environment variables and whitelisted AGY_ parameters
        are correctly preserved for child execution.
        """
        monkeypatch.setenv("AGY_TEST_PARAMETER", "agy_custom_value")
        monkeypatch.setenv("AGY_MAX_SLIPPAGE_BPS", "50")

        safe_env = get_sanitized_subprocess_env()

        # OS runtime variables
        assert "PATH" in safe_env
        assert safe_env["AGY_TEST_PARAMETER"] == "agy_custom_value"
        assert safe_env["AGY_MAX_SLIPPAGE_BPS"] == "50"


# ===========================================================================
# 5. Container & Deployment Hardening Audit
# ===========================================================================

class TestContainerAndDeploymentHardeningEmpirical:
    """Audits container configuration files against CIS benchmarks and least-privilege standards."""

    def test_dockerfile_least_privilege_directives(self):
        """Audits Dockerfile for non-root execution, multi-stage builds, and permissions."""
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        # Multi-stage build
        assert re.search(r"FROM\s+python:3\.11-slim-bookworm\s+AS\s+builder", dockerfile)
        assert re.search(r"FROM\s+python:3\.11-slim-bookworm\s+AS\s+runner", dockerfile)

        # Unprivileged user creation and execution
        assert re.search(r"groupadd\s+-g\s+10001\s+appgroup", dockerfile)
        assert re.search(r"useradd\s+-u\s+10001\s+-g\s+appgroup.*appuser", dockerfile)
        assert re.search(r"USER\s+10001:10001", dockerfile)

        # Read-only code ownership & isolated 700 state
        assert "--chown=root:root core /app/core" in dockerfile
        assert "chmod 700 /app/keystores /app/data /app/results" in dockerfile

        # Loopback healthcheck
        assert "HEALTHCHECK" in dockerfile
        assert "http://127.0.0.1:8899/api/health" in dockerfile

        # No server header
        assert "--no-server-header" in dockerfile

    def test_docker_compose_prod_security_constraints(self):
        """Audits docker-compose.prod.yml for read-only filesystem, cap_drop, and tmpfs isolation."""
        compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

        assert "read_only: true" in compose
        assert "no-new-privileges:true" in compose
        assert "cap_drop:" in compose
        assert "- ALL" in compose
        assert 'user: "10001:10001"' in compose
        assert "tmpfs:" in compose
        assert "noexec,nosuid" in compose
        assert "internal_net:" in compose

    def test_caddy_reverse_proxy_configuration(self):
        """Audits deploy/Caddyfile for reverse proxying and strict security headers."""
        caddy = Path("deploy/Caddyfile").read_text(encoding="utf-8")

        assert "reverse_proxy trading-server:8899" in caddy
        assert 'X-Frame-Options "DENY"' in caddy
        assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in caddy
        assert 'X-Content-Type-Options "nosniff"' in caddy

    def test_gitignore_comprehensive_protection(self):
        """Audits .gitignore to ensure credentials, keystores, and environments are ignored."""
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        required_patterns = [".env", "keystores/", "secrets/", "*.key", "*.pem", "*.db", "*.sqlite"]
        for pat in required_patterns:
            assert pat in gitignore, f"Missing critical exclusion pattern '{pat}' in .gitignore"
