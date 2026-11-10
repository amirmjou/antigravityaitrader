# Explorer 2 Handoff Report: Transport & Authentication Hardening Strategy

**Agent**: Explorer 2 (`teamwork_explorer_sec_it2_2`)  
**Role**: investigator, strategist, synthesizer  
**Parent Orchestrator ID**: `bcee5896-d8e8-47f7-8d44-cfee1f5051b5`  
**Working Directory**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_2\`  
**Date**: 2026-11-08T08:42:00Z  
**Type**: Hard Handoff  

---

## 1. Observation

Direct code observations, verbatim runtime exceptions, tool commands, and line references:

1. **Adversarial Suite Execution Failure (3 / 68 Failed)**:
   Command: `python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v`
   Result:
   ```
   FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestNonAsciiTokenHandling::test_non_ascii_query_token_handling
   FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestNonAsciiTokenHandling::test_non_ascii_websocket_token_handling
   FAILED tests/adversarial/test_m6_adversarial_challenge.py::TestBridgePendingTransactionExposure::test_bridge_pending_transactions_unauthenticated_exposure
   ======================== 3 failed, 65 passed in 6.06s =========================
   ```

2. **Root Cause Observation 1: Non-ASCII Token `TypeError` in `verify_token_string`**:
   - Location: `visualization/server/security.py`, lines 62–71:
     ```python
     def verify_token_string(token: Optional[str]) -> bool:
         """
         Validates a token against configured secret using constant-time comparison.
         """
         if not is_auth_enforced():
             return True
         expected = get_configured_api_key()
         if not expected or not token:
             return False
         return hmac.compare_digest(token, expected)
     ```
   - Verbatim exception trace:
     ```
     visualization\server\security.py:71: in verify_token_string
         return hmac.compare_digest(token, expected)
     E   TypeError: comparing strings with non-ASCII characters is not supported
     ```
   - Reproduction command:
     ```powershell
     python -c "import hmac; hmac.compare_digest('🔑', 'secret')"
     ```
     Output: `TypeError: comparing strings with non-ASCII characters is not supported`.
   - Python C-implementation constraint: Python's `hmac.compare_digest(a, b)` requires `a` and `b` to contain only ASCII code points (`<= 127`) when passed as `str`. When passed as `bytes`, it operates safely across arbitrary byte sequences in constant time.

3. **Root Cause Observation 2: WebSocket Handshake ASGI Crash vs. Close Code 1008**:
   - Location: `visualization/server/ws_router.py`, lines 24–27:
     ```python
     @ws_router.websocket("/ws/telemetry")
     async def websocket_telemetry_endpoint(websocket: WebSocket):
         if not check_websocket_auth(websocket):
             await websocket.close(code=1008, reason="Unauthorized")
             return
     ```
   - Location: `execution/wallet/eip1193_bridge.py`, lines 326–330:
     ```python
     @app.websocket("/ws")
     @app.websocket("/ws/status")
     async def websocket_endpoint(websocket: WebSocket):
         if not check_websocket_auth(websocket):
             await websocket.close(code=1008, reason="Unauthorized")
             return
     ```
   - Result: Because `check_websocket_auth` invoked `verify_token_string` without exception wrapping, incoming WebSocket requests with URL-encoded non-ASCII query tokens (e.g. `?token=%F0%9F%94%91` which decodes to `\U0001f511`) crashed before reaching `await websocket.close(code=1008, reason="Unauthorized")`. The unhandled exception crashed Starlette's ASGI endpoint instead of terminating cleanly with close code 1008.

4. **Root Cause Observation 3: Unprotected `GET /pending` in `eip1193_bridge.py`**:
   - Location: `execution/wallet/eip1193_bridge.py`, lines 268–270:
     ```python
     @app.get("/pending")
     async def list_pending():
         return {"pending": list(server.pending_transactions.values())}
     ```
   - Contrast with other protected endpoints in the same file:
     - `/send-transaction` (line 227): `_token: str = Depends(verify_api_token)`
     - `/sign-typed-data` (line 238): `_token: str = Depends(verify_api_token)`
     - `/confirm-transaction` (line 249): `_token: str = Depends(verify_api_token)`
     - `/rpc` (line 273): `_token: str = Depends(verify_api_token)`
   - In production mode, any unauthenticated caller querying `GET /pending` was handed the full list of pending transactions, amounts, and destination addresses.

5. **Empirical Fix Verification Output**:
   Running `tests/adversarial/test_m6_adversarial_challenge.py` with UTF-8 byte encoding and `/pending` auth applied yielded:
   ```
   ======================== 68 passed, 1 warning in 4.24s ========================
   PYTEST EXIT CODE: 0
   ```
   Running `tests/adversarial/test_security_hardening.py` yielded:
   ```
   ======================== 29 passed, 1 warning in 4.30s ========================
   PYTEST EXIT CODE: 0
   ```
   Running `tests/e2e/run_all.py` yielded:
   ```
   ============================= 200 passed in 1.13s =============================
   TEST SUITE SUMMARY: PASSED
   Total Tests Executed: 200
   ```
   Running `tests/unit/` yielded:
   ```
   ============================= 102 passed in 9.37s =============================
   ```

---

## 2. Logic Chain

1. *Observation 2* demonstrates that `hmac.compare_digest` throws `TypeError` when comparing strings with non-ASCII characters.
2. In HTTP endpoints (`/events/reasoning?token=🔑`), FastAPI catches unhandled `TypeError` inside route dependencies and converts it into HTTP 500 Internal Server Error instead of the required HTTP 401 Unauthorized.
3. In WebSocket handshakes (`/ws/telemetry?token=%F0%9F%94%91`), Starlette executes `websocket_telemetry_endpoint` within an ASGI connection loop. When `check_websocket_auth` crashes with `TypeError`, the connection loop is aborted before `websocket.close(code=1008)` executes (*Observation 3*).
4. Converting both `token` and `expected` to UTF-8 `bytes` (`token.encode("utf-8")`, `expected.encode("utf-8")`) allows `hmac.compare_digest` to perform constant-time comparison on byte sequences of any character set, eliminating the `TypeError` and maintaining resistance against timing attacks.
5. Defensively wrapping `check_websocket_auth` and `verify_api_token` in `try...except` guarantees that unexpected decoding, type errors, or malformed ASGI scopes will always return `False` or raise `HTTPException(status_code=401)`.
6. Defensively wrapping `websocket.close(code=1008)` inside the WebSocket endpoint ensures that all unauthorized connections receive WebSocket close code 1008 under all failure modes.
7. *Observation 4* shows `GET /pending` lacked `_token: str = Depends(verify_api_token)`. Adding this dependency aligns `/pending` with the existing dual-mode access control architecture, rejecting unauthenticated production requests with 401 while preserving dev-mode test execution.
8. *Observation 5* proves that these precise changes resolve all 3 failures in `test_m6_adversarial_challenge.py` (68/68 passed) while preserving 100% pass rates across all 200 E2E tests, 29 security hardening tests, and 102 unit tests with zero regressions.

---

## 3. Caveats

1. **Read-Only Scope**: Explorer 2 has strictly performed read-only investigation, live experimentation in isolated subshells, and test verification. Code changes must be applied by Worker 2.
2. **HTTP Header Non-ASCII Encoding**: Standard HTTP/1.1 RFC 7230 restricts HTTP headers (`Authorization: Bearer ...`) to ASCII/ISO-8859-1. Clients attempting to send raw UTF-8 in HTTP headers may fail client-side in libraries like `httpx` or `urllib3`. Query parameters (`?token=...`) and WebSocket query strings are the primary vectors transmitting non-ASCII tokens and emojis, which our UTF-8 byte encoding remediates.
3. **Subprotocol Authentication**: The platform currently uses query parameters (`?token=...`) and HTTP headers (`Authorization`, `X-API-Key`) for WebSocket authentication. Sec-WebSocket-Protocol token transport is not currently tested by the test suite, but would follow the identical `verify_token_string` validation logic if added.

---

## 4. Conclusion & Specific Code Remediation Plan for Worker 2

Worker 2 must apply the following specific code modifications:

### Patch 1: `visualization/server/security.py`

1. **Add `Union` to typing imports** (line 14):
   ```python
   from typing import Any, Callable, Dict, List, Optional, Union
   ```

2. **Harden `verify_token_string` with UTF-8 byte encoding & defensive exception handling** (lines 62–72):
   ```python
   def verify_token_string(token: Optional[Union[str, bytes]]) -> bool:
       """
       Validates a token against configured secret using constant-time comparison.
       Safely encodes string inputs to UTF-8 bytes to defend against non-ASCII
       TypeErrors and timing oracles. Defensively catches encoding and type exceptions.
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
       except (TypeError, ValueError, UnicodeEncodeError, AttributeError) as exc:
           logger.warning("Token verification encountered invalid payload or encoding: %s", exc)
           return False
   ```

3. **Harden `verify_api_token` against unhandled 500 errors** (lines 74–102):
   ```python
   async def verify_api_token(
       request: Request,
       credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
   ) -> str:
       """
       FastAPI dependency enforcing API authentication on protected endpoints.
       In development mode without an API key configured, allows bypass.
       In production mode (or when TRADING_API_KEY is set), verifies Bearer token,
       X-API-Key header, or ?token= query parameter.
       Safely rejects invalid, malformed, or non-ASCII tokens with HTTP 401.
       """
       if not is_auth_enforced():
           return "development_bypass"

       try:
           token: Optional[str] = None
           if credentials and credentials.credentials:
               token = credentials.credentials
           elif "x-api-key" in request.headers:
               token = request.headers["x-api-key"]
           elif "token" in request.query_params:
               token = request.query_params["token"]

           if not token or not verify_token_string(token):
               raise HTTPException(
                   status_code=status.HTTP_401_UNAUTHORIZED,
                   detail="Unauthorized",
                   headers={"WWW-Authenticate": "Bearer"},
               )
           return token
       except HTTPException:
           raise
       except Exception as exc:
           logger.warning("verify_api_token encountered unexpected exception: %s", exc)
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Unauthorized",
               headers={"WWW-Authenticate": "Bearer"},
           )
   ```

4. **Harden `check_websocket_auth` against unhandled ASGI crashes** (lines 104–121):
   ```python
   def check_websocket_auth(websocket: WebSocket) -> bool:
       """
       Validates authentication for incoming WebSocket connections.
       Checks query parameter ?token=<TOKEN> or Authorization / X-API-Key headers.
       Defensively catches all exceptions to prevent unhandled ASGI connection crashes.
       """
       try:
           if not is_auth_enforced():
               return True

           token: Optional[str] = None
           if "token" in websocket.query_params:
               token = websocket.query_params.get("token")

           if not token:
               auth_header = websocket.headers.get("authorization", "")
               if auth_header and auth_header.lower().startswith("bearer "):
                   token = auth_header[7:].strip()
               elif "x-api-key" in websocket.headers:
                   token = websocket.headers.get("x-api-key")

           if not token:
               return False

           return verify_token_string(token)
       except Exception as exc:
           logger.warning("WebSocket authentication verification exception: %s", exc)
           return False
   ```

---

### Patch 2: `visualization/server/ws_router.py`

**Ensure clean WebSocket closure with code 1008 under all exception conditions** (lines 24–28):
```python
    try:
        is_authed = check_websocket_auth(websocket)
    except Exception as exc:
        logger.warning("WebSocket auth check exception on /ws/telemetry: %s", exc)
        is_authed = False

    if not is_authed:
        try:
            await websocket.close(code=1008, reason="Unauthorized")
        except Exception as exc:
            logger.debug("WebSocket close(1008) failed or already closed: %s", exc)
        return
```

---

### Patch 3: `execution/wallet/eip1193_bridge.py`

1. **Protect `GET /pending` with `verify_api_token` dependency** (lines 268–270):
   ```python
   # Replace:
   @app.get("/pending")
   async def list_pending():
       return {"pending": list(server.pending_transactions.values())}

   # With:
   @app.get("/pending")
   async def list_pending(_token: str = Depends(verify_api_token)):
       return {"pending": list(server.pending_transactions.values())}
   ```

2. **Harden WebSocket close with code 1008 on bridge endpoint** (lines 326–331):
   ```python
   # Replace:
           if not check_websocket_auth(websocket):
               await websocket.close(code=1008, reason="Unauthorized")
               return

   # With:
           try:
               is_authed = check_websocket_auth(websocket)
           except Exception as exc:
               logger.warning("Bridge WebSocket auth check exception: %s", exc)
               is_authed = False

           if not is_authed:
               try:
                   await websocket.close(code=1008, reason="Unauthorized")
               except Exception as exc:
                   logger.debug("Bridge WebSocket close(1008) failed or already closed: %s", exc)
               return
   ```

---

## 5. Verification Method

Once Worker 2 applies the patches, execute the following commands to independently verify the complete fix:

1. **Adversarial Challenge Suite (Must achieve 68/68 passed)**:
   ```powershell
   python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v
   ```
   *Expected Result*: All 68 tests pass, specifically:
   - `test_non_ascii_query_token_handling PASSED`
   - `test_non_ascii_websocket_token_handling PASSED`
   - `test_bridge_pending_transactions_unauthenticated_exposure PASSED`

2. **Security Hardening Baseline Suite (Must achieve 29/29 passed)**:
   ```powershell
   python -m pytest tests/adversarial/test_security_hardening.py -v
   ```
   *Expected Result*: 29 passed.

3. **Full Platform E2E Regression Suite (Must achieve 200/200 passed)**:
   ```powershell
   python tests/e2e/run_all.py
   ```
   *Expected Result*: 200 passed in ~2 seconds with zero regressions.

4. **Unit Test Suite (Must achieve 102/102 passed)**:
   ```powershell
   python -m pytest tests/unit/ -v
   ```
   *Expected Result*: 102 passed.

5. **Direct Verification One-Liner for Non-ASCII Token**:
   ```powershell
   python -c "from visualization.server.security import verify_token_string; import os; os.environ['TRADINGAGENTS_SECURITY_MODE']='production'; os.environ['TRADING_API_KEY']='key123'; print('Non-ASCII token result:', verify_token_string('🔑'))"
   ```
   *Expected Output*: `Non-ASCII token result: False` (no exception raised).

6. **Direct Verification One-Liner for Bridge /pending 401 Rejection**:
   ```powershell
   python -c "from execution.wallet.eip1193_bridge import EIP1193BridgeServer; from fastapi.testclient import TestClient; import os; os.environ['TRADINGAGENTS_SECURITY_MODE']='production'; os.environ['TRADING_API_KEY']='key123'; s = EIP1193BridgeServer(); client = TestClient(s.app); res = client.get('/pending'); print('Status:', res.status_code)"
   ```
   *Expected Output*: `Status: 401`.
