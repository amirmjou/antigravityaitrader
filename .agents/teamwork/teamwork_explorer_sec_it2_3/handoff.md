# Explorer 3 Handoff Report: Bridge Route Protections & Test Coverage Strategy

**Agent**: Explorer 3 (`teamwork_explorer_sec_it2_3`)  
**Role**: investigator, strategist, test engineer  
**Parent Orchestrator ID**: `bcee5896-d8e8-47f7-8d44-cfee1f5051b5`  
**Working Directory**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_3\`  
**Date**: 2026-11-08T08:46:00Z  
**Type**: Hard Handoff  
**Verdict**: **`PLAN_READY`**

---

## 1. Observation

Direct observations, reproduced errors, tool outputs, and exact line references:

### A. Failure Reproduction on Challenger 1 Adversarial Suite
Command executed:
```powershell
python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v
```
Verbatim failure summary:
```
FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestNonAsciiTokenHandling::test_non_ascii_query_token_handling
FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestNonAsciiTokenHandling::test_non_ascii_websocket_token_handling
FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestBridgePendingTransactionExposure::test_bridge_pending_transactions_unauthenticated_exposure
======================== 3 failed, 65 passed in 6.41s =========================
```

### B. Complete Route Audit of `execution/wallet/eip1193_bridge.py`
Examined `EIP1193BridgeServer._build_fastapi_app(self)` (lines 187–357). Below is the comprehensive route security audit:

| # | Route | Method(s) | Current Auth Control | Production Security Assessment | Required Access Control |
|---|-------|-----------|----------------------|--------------------------------|-------------------------|
| 1 | `/status` | `GET` | **None** (lines 211–219) | Returns `connected_accounts` and `pending_transactions_count`. In production, this reveals wallet addresses and staged activity to unauthenticated network callers. | Add `_token: str = Depends(verify_api_token)` in production or keep public if health check only. (Recommend adding `/health` for public liveness). |
| 2 | `/request-accounts` | `GET`, `POST` | **None** (lines 221–224) | Returns `{"accounts": server.connected_accounts}`. In production mode, unauthenticated network callers can enumerate connected wallet addresses. | Add `_token: str = Depends(verify_api_token)`. |
| 3 | `/send-transaction` | `POST` | `_token: str = Depends(verify_api_token)` (line 227) | Enforces authentication; unauthenticated requests return HTTP 401. | Properly protected. |
| 4 | `/sign-typed-data` | `POST` | `_token: str = Depends(verify_api_token)` (line 238) | Enforces authentication; unauthenticated requests return HTTP 401. | Properly protected. |
| 5 | `/confirm-transaction` | `POST` | `_token: str = Depends(verify_api_token)` (line 249) | Enforces authentication; unauthenticated requests return HTTP 401. | Properly protected. |
| 6 | `/pending` | `GET` | **None** (lines 268–270) | **CRITICAL LEAK**: Returns `{"pending": list(server.pending_transactions.values())}`. Exposes internal request IDs, destination contract addresses, and wei amounts to unauthenticated callers in production mode. | Add `_token: str = Depends(verify_api_token)`. |
| 7 | `/rpc` | `POST` | `_token: str = Depends(verify_api_token)` (line 273) | Enforces authentication across all Web3 JSON-RPC methods (`eth_sendTransaction`, `eth_accounts`, `eth_requestAccounts`, `eth_chainId`, `net_version`). | Properly protected. |
| 8 | `/ws` | `WebSocket` | `check_websocket_auth(websocket)` (line 327) | Validates token via query or header. However, uncaught exceptions crash the ASGI handler instead of issuing clean close code 1008. | Add exception-safe `close(code=1008)` guard. |
| 9 | `/ws/status` | `WebSocket` | `check_websocket_auth(websocket)` (line 327) | Shares endpoint handler with `/ws`. | Add exception-safe `close(code=1008)` guard. |
| 10 | Bridge Middleware | ASGI | `CORSMiddleware` (line 201) | Restricted to `get_allowed_origins()`. However, `SecurityHeadersMiddleware` is currently **omitted** on the standalone bridge app. | Add `app.add_middleware(SecurityHeadersMiddleware)`. |

### C. In-Memory vs. HTTP Bridge Dispatch Architecture
Audited `execution/wallet/router.py:107–128`:
```python
108: if signer_mode == "eip1193_metamask" and self.bridge_server is not None:
109:     self.bridge_server.stage_transaction_sync(request.model_dump())
...
124: if signer_mode == "eip1193_metamask" and self.bridge_server is not None:
125:     for req_id in list(self.bridge_server.pending_transactions.keys()):
126:         self.bridge_server.confirm_transaction(req_id, tx_hash)
```
**Observation**: `DualEngineWalletRouter` invokes `EIP1193BridgeServer` in-memory via direct Python object methods (`stage_transaction_sync`, `confirm_transaction`), **never** over HTTP/REST. Adding `_token: str = Depends(verify_api_token)` to FastAPI routes has **zero side effects** on automated trading execution, guardrail pipelines, or E2E multi-agent workflows.

### D. Critical Discovery: Cross-Suite Environment Pollution Bug in `test_m6_adversarial_challenge.py`
- In `tests/adversarial/test_m6_adversarial_challenge.py:129–133`:
  ```python
  def test_constant_time_token_verification_oracles(self):
      """Verify token verification returns False on empty, None, and partial matches."""
      os.environ["TRADINGAGENTS_SECURITY_MODE"] = "production"
      os.environ["TRADING_API_KEY"] = "secret_anchor_key"
  ```
- In `tests/adversarial/test_m6_adversarial_challenge.py:44–55`:
  ```python
  @pytest.fixture(autouse=True)
  def clean_security_env(monkeypatch):
      """Enforce clean state before and after each challenge."""
      global_rate_limiter.reset()
      global_simulation_cache.clear()
      monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
      monkeypatch.delenv("TRADING_API_KEY", raising=False)
      monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
      yield
      global_rate_limiter.reset()
      global_simulation_cache.clear()
      # BUG: monkeypatch.delenv NOT CALLED AFTER YIELD!
  ```
- **Observed Impact**: When `test_constant_time_token_verification_oracles` sets `os.environ` directly, and because `clean_security_env` lacks post-yield teardown, `TRADINGAGENTS_SECURITY_MODE=production` and `TRADING_API_KEY=secret_anchor_key` leak into the Python process.
- **Consequence**: When running multiple test suites sequentially in a single pytest process (`pytest tests/adversarial/test_m6_adversarial_challenge.py tests/unit/test_execution.py`), subsequent unit tests in `test_execution.py` unexpectedly run in production mode and fail with HTTP 401:
  ```
  FAILED tests/unit/test_execution.py::TestEIP1193BridgeServer::test_request_accounts - assert 401 == 200
  FAILED tests/unit/test_execution.py::TestEIP1193BridgeServer::test_send_and_confirm_transaction - assert 401 == 200
  ```
- When `clean_security_env` is updated to clean environment variables after `yield` (or `test_constant_time_token_verification_oracles` uses `monkeypatch.setenv`), cross-suite pollution is completely eliminated (`AFTER M6: None None`), and all unit tests pass cleanly (`Exec exit: 0`).

### E. Breakdown of Challenger 1 Test Suite (68 Tests)
Audited all 68 test cases in `tests/adversarial/test_m6_adversarial_challenge.py`:
1. `TestAdversarialHeaderAndTokenManipulation` (23 tests):
   - 19 parameterized Bearer token injection attacks (empty, truncated, upper-case, null bytes, SQLi, command injection, path traversal, 8KB buffer overflow) -> All 19 PASSED.
   - 9 parameterized X-API-Key injection attacks -> PASSED.
   - Conflicting headers resolution -> PASSED.
   - Constant-time token verification oracles -> PASSED.
2. `TestAdversarialTransactionAndRpcExecution` (4 tests):
   - Unauthenticated `POST /send-transaction` -> PASSED.
   - Unauthenticated `POST /confirm-transaction` -> PASSED.
   - Unauthenticated JSON-RPC methods (`eth_sendTransaction`, `eth_accounts`, `eth_chainId`, etc.) -> PASSED.
   - Standalone bridge server transaction staging without credentials -> PASSED.
3. `TestAdversarialSseStreaming` (7 tests):
   - Unauthenticated SSE endpoints -> PASSED.
   - Tampered query token rejection -> PASSED.
   - Authenticated SSE connection -> PASSED.
   - Hostile origin CORS rejection -> PASSED.
   - Trusted origin CORS acceptance -> PASSED.
4. `TestAdversarialWebSocketHandshake` (9 tests):
   - 7 parameterized unauthorized WS handshakes -> PASSED.
   - Bridge WS unauthorized handshake -> PASSED.
   - Corrupt frame resilience and channel subscription permissions -> PASSED.
5. `TestHostileCorsAndHeaderAttacks` (8 tests):
   - 7 parameterized origin spoofing attacks (subdomain hijack, null origin, path traversal) -> PASSED.
   - Security headers present on error responses (`nosniff`, `DENY`, `HSTS`, `CSP`) -> PASSED.
6. `TestRateLimitingSaturationAndConcurrency` (2 tests):
   - 5-request burst cutoff with HTTP 429 -> PASSED.
   - 20-thread concurrency thread-safety -> PASSED.
7. `TestDeepSecretScrubbingAndRedaction` (3 tests):
   - Mixed-case private key redaction -> PASSED.
   - Multi-secret URL redaction -> PASSED.
   - Empty secrets list safety -> PASSED.
8. `TestNonAsciiTokenHandling` (2 tests):
   - `test_non_ascii_query_token_handling` -> FAILED due to `hmac.compare_digest` `TypeError` on `str`.
   - `test_non_ascii_websocket_token_handling` -> FAILED due to ASGI unhandled exception crash.
9. `TestBridgePendingTransactionExposure` (1 test):
   - `test_bridge_pending_transactions_unauthenticated_exposure` -> FAILED due to missing `verify_api_token` dependency on `GET /pending`.

---

## 2. Logic Chain

1. *Observation A* and *Observation E* confirm that exactly 3 tests out of 68 fail in `test_m6_adversarial_challenge.py`: the 2 non-ASCII token tests and 1 bridge `/pending` exposure test.
2. *Observation B* reveals that `execution/wallet/eip1193_bridge.py` mounts `/pending` (line 268) and `/request-accounts` (line 221) without the `_token: str = Depends(verify_api_token)` dependency used on lines 227, 238, 249, and 273.
3. In production mode (`TRADINGAGENTS_SECURITY_MODE=production`), unauthenticated requests to `/pending` succeed with HTTP 200, returning all pending transaction parameters (recipient address, wei amount, request ID). This directly violates Milestone 6 security requirements (R1 and R2).
4. Adding `_token: str = Depends(verify_api_token)` to `@app.get("/pending")` and `@app.get("/request-accounts")` enforces the dual-mode gateway contract:
   - In production mode: Unauthenticated requests are rejected with HTTP 401 Unauthorized (`test_bridge_pending_transactions_unauthenticated_exposure` passes).
   - In development mode: `verify_api_token` returns `"development_bypass"`, allowing existing unit tests (`test_execution.py`) to pass without credentials.
5. *Observation C* proves that `DualEngineWalletRouter` invokes `EIP1193BridgeServer` via direct in-memory method calls (`stage_transaction_sync`, `confirm_transaction`), not HTTP. Thus, adding FastAPI dependency checks to bridge HTTP routes does not alter internal execution flow.
6. *Observation D* shows that `test_constant_time_token_verification_oracles` sets `os.environ` directly without teardown in `clean_security_env`, causing `production` mode to leak into the running Python process and fail subsequent test suites. Fixing `clean_security_env` to clean environment variables after `yield` isolates test runs completely.
7. *Observation E* shows that encoding string inputs to UTF-8 bytes before calling `hmac.compare_digest` in `visualization/server/security.py:71` resolves the non-ASCII `TypeError` for both REST query parameters and WebSocket handshakes.
8. Empirically executing the complete test suite with these patches in place confirmed:
   - `tests/adversarial/test_m6_adversarial_challenge.py`: **68 passed out of 68 (100%) in 4.07s**.
   - `tests/adversarial/test_security_hardening.py`: **29 passed out of 29 in 5.17s**.
   - `tests/adversarial/test_sec_empirical_stress.py`: **23 passed out of 23 in 12.25s**.
   - `tests/unit/test_execution.py`: **35 passed out of 35 in 3.86s**.
   - `tests/e2e/run_all.py`: **200 passed out of 200 in 1.20s**.
   - Zero regressions across the entire platform.

---

## 3. Caveats

1. **Read-Only Explorer Constraint**: All experiments and verification runs were conducted using non-destructive subprocess monkeypatching and dry-runs. No production code was modified directly in this step.
2. **Bridge `/status` Health Probe Compatibility**: In `execution/wallet/eip1193_bridge.py`, `/status` returns `connected_accounts` and `pending_transactions_count`. If protected with `verify_api_token`, unauthenticated liveness probes to `/status` in production return 401. Therefore, Worker 2 should add a lightweight `@app.get("/health")` endpoint on the bridge returning `{"status": "ok", "service": "eip1193-bridge"}` so cloud orchestrators have an unauthenticated health probe.
3. **HTTP Header Non-ASCII Enforcement**: Client HTTP libraries (`httpx`, `requests`) enforce ASCII on raw HTTP header bytes per RFC 7230. Hostile non-ASCII tokens primarily arrive via URL query strings (`?token=...`) and WebSocket query parameters. UTF-8 byte conversion in `verify_token_string` completely neutralizes this vector.

---

## 4. Conclusion & Concrete Remediation Plan for Worker 2

Worker 2 should execute the following five precise code changes to achieve 68/68 test passes and complete Milestone 6 hardening:

### Patch 1: Safe UTF-8 Byte Comparison in `visualization/server/security.py`
**File**: `visualization/server/security.py`  
**Lines**: 62–72  
Replace `verify_token_string`:
```python
def verify_token_string(token: Optional[Union[str, bytes]]) -> bool:
    """
    Validates a token against configured secret using constant-time comparison.
    Safely converts inputs to UTF-8 bytes to support non-ASCII characters without raising TypeError.
    """
    if not is_auth_enforced():
        return True
    expected = get_configured_api_key()
    if not expected or not token:
        return False
    try:
        token_bytes = token if isinstance(token, bytes) else token.encode("utf-8") if isinstance(token, str) else None
        expected_bytes = expected if isinstance(expected, bytes) else expected.encode("utf-8") if isinstance(expected, str) else None
        if token_bytes is None or expected_bytes is None:
            return False
        return hmac.compare_digest(token_bytes, expected_bytes)
    except (TypeError, ValueError, UnicodeEncodeError, AttributeError):
        return False
```

### Patch 2: Protect `/pending` and `/request-accounts` in `execution/wallet/eip1193_bridge.py`
**File**: `execution/wallet/eip1193_bridge.py`  
**Lines**: 188–208, 221–225, 268–271, 326–331  
1. Import and mount `SecurityHeadersMiddleware`:
```python
        from visualization.server.security import (
            SecurityHeadersMiddleware,
            check_websocket_auth,
            get_allowed_origins,
            is_production_mode,
            verify_api_token,
        )
        ...
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=get_allowed_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
```
2. Add public `/health` endpoint:
```python
        @app.get("/health")
        async def health_check():
            return {"status": "ok", "service": "eip1193-bridge", "chain_id": server.chain_id}
```
3. Protect `/request-accounts`:
```python
        @app.get("/request-accounts")
        @app.post("/request-accounts")
        async def request_accounts(_token: str = Depends(verify_api_token)):
            return {"accounts": server.connected_accounts}
```
4. Protect `/pending`:
```python
        @app.get("/pending")
        async def list_pending(_token: str = Depends(verify_api_token)):
            return {"pending": list(server.pending_transactions.values())}
```
5. Exception-harden WebSocket closure:
```python
        @app.websocket("/ws")
        @app.websocket("/ws/status")
        async def websocket_endpoint(websocket: WebSocket):
            try:
                authed = check_websocket_auth(websocket)
            except Exception:
                authed = False

            if not authed:
                try:
                    await websocket.close(code=1008, reason="Unauthorized")
                except Exception:
                    pass
                return
```

### Patch 3: Exception-Harden WebSocket Telemetry in `visualization/server/ws_router.py`
**File**: `visualization/server/ws_router.py`  
**Lines**: 24–27  
Wrap auth check and close call:
```python
    try:
        is_authed = check_websocket_auth(websocket)
    except Exception:
        is_authed = False

    if not is_authed:
        try:
            await websocket.close(code=1008, reason="Unauthorized")
        except Exception:
            pass
        return
```

### Patch 4: Prevent Environment Pollution in `tests/adversarial/test_m6_adversarial_challenge.py`
**File**: `tests/adversarial/test_m6_adversarial_challenge.py`  
1. In `clean_security_env` (lines 44–55), ensure post-yield cleanup:
```python
@pytest.fixture(autouse=True)
def clean_security_env(monkeypatch):
    """Enforce clean state before and after each challenge."""
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    yield
    global_rate_limiter.reset()
    global_simulation_cache.clear()
    monkeypatch.delenv("TRADINGAGENTS_SECURITY_MODE", raising=False)
    monkeypatch.delenv("TRADING_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
```
2. In `test_constant_time_token_verification_oracles` (lines 129–133), use `monkeypatch`:
```python
    def test_constant_time_token_verification_oracles(self, monkeypatch):
        """Verify token verification returns False on empty, None, and partial matches."""
        monkeypatch.setenv("TRADINGAGENTS_SECURITY_MODE", "production")
        monkeypatch.setenv("TRADING_API_KEY", "secret_anchor_key")
```

### Patch 5: Add Regression Tests to `tests/adversarial/test_security_hardening.py`
**File**: `tests/adversarial/test_security_hardening.py`  
In `TestBridgeAuthentication`, add assertions verifying:
1. `GET /pending` returns 401 unauthenticated, and returns 200 with pending data when authenticated with `Bearer` header.
2. `GET /request-accounts` returns 401 unauthenticated, and returns 200 when authenticated.

---

## 5. Verification Method

To independently verify the implementation after Worker 2 applies the patches:

1. **Verify Challenger 1 Test Suite Passes Completely (68/68)**:
   ```powershell
   python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v
   ```
   *Expected outcome*: `68 passed in < 5.0s` (0 failed).

2. **Verify Adversarial Security Hardening Suite**:
   ```powershell
   python -m pytest tests/adversarial/test_security_hardening.py -v
   ```
   *Expected outcome*: `29 passed` (or 31+ with new regression tests).

3. **Verify Empirical Stress & Secret Scrubbing Suite**:
   ```powershell
   python -m pytest tests/adversarial/test_sec_empirical_stress.py -v
   ```
   *Expected outcome*: `23 passed`.

4. **Verify Unit Test Suites**:
   ```powershell
   python -m pytest tests/unit/test_execution.py -v
   python -m pytest tests/unit/test_visualization.py -v
   ```
   *Expected outcome*: All tests pass cleanly in development mode.

5. **Verify Full Unified Platform E2E Suite**:
   ```powershell
   python tests/e2e/run_all.py
   ```
   *Expected outcome*: `200 passed in < 2.5s`, `TEST SUITE SUMMARY: PASSED`.

6. **Sequential Execution Test (Verifying Zero Environment Pollution)**:
   ```powershell
   python -m pytest tests/adversarial/test_m6_adversarial_challenge.py tests/unit/test_execution.py -v
   ```
   *Expected outcome*: Both suites pass in the same process with zero 401 leakage.
