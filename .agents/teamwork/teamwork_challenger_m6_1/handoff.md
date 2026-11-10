# Handoff Report: Live Endpoint Adversarial Challenge (Milestone 6)

**Agent**: `teamwork_challenger_m6_1`  
**Role**: Live Endpoint Adversarial Challenger (critic, specialist)  
**Date**: 2026-11-09T03:08:00Z  
**Recipient**: Orchestrator (`56b3c564-3f59-4841-ab4a-c6a6e410c34a`)  
**Working Directory**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m6_1\`  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

Direct empirical stress testing and dynamic code execution against the live terminal server, authentication gate, WebSocket telemetry, and MetaMask bridge routes (`visualization/server/app.py`, `visualization/server/security.py`, `run_live_metamask_terminal.py`, `execution/wallet/eip1193_bridge.py`) using the newly authored adversarial stress test suite (`tests/adversarial/test_m6_live_endpoint_stress.py`) revealed the following verified behaviors:

### 1.1 Verified Robust Controls (Passes)
1. **Auth Gate Token Enforcement (`GET /`, `GET /dashboard`, `GET /events/reasoning`, `WS /ws/telemetry`)**:
   - Tested 11 hostile token permutations: empty string (`""`), whitespace (`"   "`), truncated token (`ag_live_metamask_2026_toke`), appended token (`ag_live_metamask_2026_token_extra`), case-flipped (`AG_LIVE_METAMASK_2026_TOKEN`), URL-encoded null byte (`ag_live_metamask_2026_token%00`), Unicode emoji (`\U0001F511`), buffer overflow (4KB `"A"*4096`), SQL injection (`' OR '1'='1`), and XSS tags (`<script>alert(1)</script>`).
   - `GET /` returned `401 Unauthorized` across all hostile tokens.
   - `GET /dashboard` returned `401 Unauthorized` across all hostile tokens.
   - `GET /events/reasoning` returned `401 Unauthorized` across all hostile tokens.
   - `WS /ws/telemetry` rejected handshakes with WebSocket code `1008 (Unauthorized)` across all hostile tokens.
   - Valid session token (`ag_live_metamask_2026_token`) returned `200 OK` HTML on `/` and `/dashboard`, `200 OK text/event-stream` on `/events/reasoning`, and established active session on `WS /ws/telemetry`.
   - In development mode (unset security mode and API key), `GET /` and `GET /dashboard` returned `200 OK` without regression.

2. **Rate Limiting Burst Saturation (`POST /wallet_syncAccount`)**:
   - Sent a burst of 40 sequential requests from client `127.0.0.1`.
   - Exactly the first 30 requests returned `200 OK`.
   - Requests 31 through 40 were strictly blocked and returned `429 Too Many Requests`.
   - Executed 40 concurrent requests across 10 worker threads (`ThreadPoolExecutor`): exactly 30 succeeded (`200`), and 10 were denied (`429`), demonstrating thread safety of `RateLimiter`.

3. **WebSocket Concurrency & Fault Tolerance (`WS /ws/telemetry`)**:
   - Executed 20 rapid sequential connect / disconnect cycles with pings: zero crashes, leaks, or hung connections.
   - Connected 5 concurrent persistent WebSockets: each successfully received initial state snapshots (`ticker_update`, `orderbook_snapshot`, `indicator_update`, `guardrail_state`) and responsive `pong` frames.
   - Injected non-JSON junk strings and unauthorized channels (`malicious_admin_exec`): the connection survived, ignored invalid syntax, and acknowledged only valid channels (`ticker`, `orderbook`).

---

### 1.2 Empirically Discovered Vulnerabilities & Failure Modes

#### Vulnerability 1: Unhandled `AttributeError` / HTTP 500 Crash on Non-Dict Payloads (`POST /wallet_syncAccount`)
- **Location**: `visualization/server/app.py:238–241`
  ```python
  body = await request.json()
  params = body.get("params") if isinstance(body.get("params"), list) else []
  account = body.get("account") or body.get("address") or (params[0] if params else None)
  chain_id = body.get("chain_id") or (params[1] if len(params) > 1 else None)
  ```
- **Observed Behavior**:
  If a client submits a valid JSON array (e.g. `["0x1234567890123456789012345678901234567890", 42161]`) or JSON primitives (`"string"`, `123`, `null`), Starlette's `request.json()` parses the body as a Python `list`, `str`, `int`, or `NoneType`.
  The immediate call to `body.get("params")` raises:
  `AttributeError: 'list' object has no attribute 'get'` (or `'str' object has no attribute 'get'`).
  FastAPI does not handle this, causing an unhandled HTTP 500 Internal Server Error instead of HTTP 400 Bad Request or HTTP 422 Unprocessable Entity.
- **Empirical Execution**:
  Command:
  ```powershell
  python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app, raise_server_exceptions=False); token = 'ag_live_metamask_2026_token'; headers = {'Authorization': f'Bearer {token}'}; res = client.post('/wallet_syncAccount', json=['0x123', 42161], headers=headers); print('Status:', res.status_code, res.text)"
  ```
  Result:
  ```
  Status: 500 Internal Server Error
  ```

#### Vulnerability 2: Unhandled `TypeError` / HTTP 500 Crash on Non-Scalar `chain_id` in `/wallet_syncAccount`
- **Location**: `visualization/server/app.py:246–249`
  ```python
  if chain_id is not None:
      try:
          cid = int(str(chain_id), 16) if str(chain_id).startswith("0x") else int(chain_id)
          app.state.bridge_server.chain_id = cid
      except ValueError:
          pass
  ```
- **Observed Behavior**:
  If a caller submits a non-scalar `chain_id` (e.g., `{"chain_id": [1, 2]}` or `{"chain_id": {"id": 1}}`), `str(chain_id)` is `"[1, 2]"`, which does not start with `"0x"`. The code then executes `int(chain_id)`.
  In Python, calling `int([1, 2])` raises `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'list'`.
  Because the code only catches `except ValueError:`, the `TypeError` escapes and crashes the handler with HTTP 500 Internal Server Error.
- **Empirical Execution**:
  Command:
  ```powershell
  python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app, raise_server_exceptions=False); token = 'ag_live_metamask_2026_token'; headers = {'Authorization': f'Bearer {token}'}; res = client.post('/wallet_syncAccount', json={'account': '0x1234567890123456789012345678901234567890', 'chain_id': [1, 2]}, headers=headers); print('Status:', res.status_code)"
  ```
  Result:
  ```
  Status: 500
  ```

#### Vulnerability 3: Unhandled `TypeError` / HTTP 500 Crash on Non-Scalar `chain_id` in `/rpc`
- **Location**: `visualization/server/app.py:216–220`
  ```python
  elif method == "wallet_syncAccount":
      params = rpc_req.params or []
      if params and isinstance(params[0], str):
          addr = params[0]
          app.state.bridge_server.set_connected_account(addr)
          if len(params) > 1 and params[1]:
              try:
                  cid = int(str(params[1]), 16) if str(params[1]).startswith("0x") else int(params[1])
                  app.state.bridge_server.chain_id = cid
              except ValueError:
                  pass
  ```
- **Observed Behavior**:
  Calling `POST /rpc` with method `"wallet_syncAccount"` and `params: ["0x1234...", [1, 2]]` triggers the exact same `int(params[1])` `TypeError` crash, returning HTTP 500 Internal Server Error.
- **Empirical Execution**:
  Command:
  ```powershell
  python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app, raise_server_exceptions=False); token = 'ag_live_metamask_2026_token'; headers = {'Authorization': f'Bearer {token}'}; res = client.post('/rpc', json={'jsonrpc': '2.0', 'method': 'wallet_syncAccount', 'params': ['0x1234567890123456789012345678901234567890', [1, 2]], 'id': 1}, headers=headers); print('Status:', res.status_code)"
  ```
  Result:
  ```
  Status: 500
  ```

#### Vulnerability 4: Missing Address Validation & State Pollution (Non-Hex & XSS Strings Accepted)
- **Location**: `visualization/server/app.py:242–254` & `execution/wallet/eip1193_bridge.py:121–123`
- **Observed Behavior**:
  Line 242 tests only `if account and isinstance(account, str):`. Any arbitrary string, including non-hex addresses (`"not_an_eth_address"`, `<script>alert(1)</script>`, or 100KB strings) is accepted and inserted into `app.state.bridge_server.connected_accounts`.
  This malicious address is subsequently:
  1. Broadcast over SSE `agent_thought` events without sanitization (`f"MetaMask Wallet Connected: {account}..."`).
  2. Picked as `active_wallet = bridge.connected_accounts[0]` in `run_live_metamask_terminal.py:207`.
  3. Propagated to multi-agent debate thoughts and trade proposal snapshots (`"wallet": active_wallet`), streaming directly to browser clients where it introduces stored XSS and UI layout corruption.
- **Empirical Execution**:
  Command:
  ```powershell
  python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app, raise_server_exceptions=False); token = 'ag_live_metamask_2026_token'; headers = {'Authorization': f'Bearer {token}'}; res = client.post('/wallet_syncAccount', json={'account': 'not_an_eth_address', 'chain_id': 42161}, headers=headers); print('Result:', res.status_code, res.json())"
  ```
  Result:
  ```
  Result: 200 {'status': 'synchronized', 'connected_accounts': ['not_an_eth_address', '0xUserWallet'], 'chain_id': 42161}
  ```

#### Vulnerability 5: Missing Chain ID Validation (Negative & Zero Chain IDs Accepted, Violating EIP-155)
- **Location**: `visualization/server/app.py:246–248`
- **Observed Behavior**:
  EIP-155 mandates that EVM chain IDs must be strictly positive integers ($> 0$).
  Submitting `{"chain_id": -1}` or `{"chain_id": -42161}` parses successfully as `cid = -1` and sets `bridge_server.chain_id = -1`.
  Subsequent JSON-RPC queries to `/rpc` with `method: "eth_chainId"` return `result: "-0x1"`, corrupting MetaMask network synchronization.
- **Empirical Execution**:
  Command:
  ```powershell
  python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app, raise_server_exceptions=False); token = 'ag_live_metamask_2026_token'; headers = {'Authorization': f'Bearer {token}'}; res = client.post('/wallet_syncAccount', json={'account': '0x1234567890123456789012345678901234567890', 'chain_id': -1}, headers=headers); print('Result:', res.status_code, res.json())"
  ```
  Result:
  ```
  Result: 200 {'status': 'synchronized', 'connected_accounts': ['0x1234567890123456789012345678901234567890', '0xUserWallet'], 'chain_id': -1}
  ```

---

## 2. Logic Chain

1. **Premise**: In production server implementations, endpoints receiving external untrusted payloads must never crash with unhandled 500 Internal Server Errors when receiving malformed JSON, lists, or non-scalar types. Furthermore, financial bridges interfacing with Web3 wallets must validate address format (valid 42-char 0x-prefixed hex string) and chain ID ($> 0$ under EIP-155) to prevent state pollution and client-side injection.
2. **Deduction from Observation 1.2 (Vulnerabilities 1, 2, 3)**:
   - In `direct_wallet_sync_account` (`visualization/server/app.py:238`), the absence of `isinstance(body, dict)` before calling `body.get()` guarantees that any non-dict JSON body raises `AttributeError`.
   - In both `direct_wallet_sync_account` (`visualization/server/app.py:246`) and `json_rpc_proxy` (`visualization/server/app.py:216`), `except ValueError:` fails to catch `TypeError` when `chain_id` or `params[1]` is a list or dict.
   - These exceptions ungracefully terminate request processing and return HTTP 500, exposing server fragility.
3. **Deduction from Observation 1.2 (Vulnerabilities 4, 5)**:
   - In `direct_wallet_sync_account`, any non-empty string is assigned to `bridge_server.connected_accounts`.
   - The lack of a regex check (e.g. `re.match(r"^0x[0-9a-fA-F]{40}$", account)`) allows arbitrary strings and XSS vectors to be broadcast in SSE deliberation events (`agent_thought`, `debate_turn`) and embedded in multi-agent trading proposals (`proposal_generated`).
   - The lack of a range check `cid > 0` allows negative chain IDs to corrupt bridge status and EIP-1193 RPC responses (`eth_chainId`).
4. **Conclusion**:
   - The live server endpoints successfully meet authentication, rate limiting, and WebSocket concurrency requirements, but FAIL robustness, input validation, and boundary safety requirements on the MetaMask bridge endpoints.
   - Therefore, the required verdict is **REQUEST_CHANGES**.

---

## 3. Caveats

- **No Caveats**: All observations are verified directly against the running application code using automated test harnesses.

---

## 4. Conclusion & Required Changes

**Verdict**: **REQUEST_CHANGES**

To resolve all identified vulnerabilities, the worker must implement the following specific hardening fixes in `visualization/server/app.py`:

### Actionable Remediation Specification:

1. **Payload Type Guard in `/wallet_syncAccount`**:
   In `visualization/server/app.py:238`:
   ```python
   try:
       body = await request.json()
   except Exception:
       raise HTTPException(status_code=400, detail="Invalid JSON payload")

   if not isinstance(body, dict):
       if isinstance(body, list) and len(body) > 0:
           # Support RPC-style array: ["0x...", chain_id]
           params = body
           account = params[0] if isinstance(params[0], str) else None
           chain_id = params[1] if len(params) > 1 else None
       else:
           raise HTTPException(status_code=400, detail="Payload must be a JSON object or array")
   else:
       params = body.get("params") if isinstance(body.get("params"), list) else []
       account = body.get("account") or body.get("address") or (params[0] if params else None)
       chain_id = body.get("chain_id") or (params[1] if len(params) > 1 else None)
   ```

2. **Ethereum Address Format Validation**:
   Validate that `account` matches Ethereum hex address format before modifying state:
   ```python
   import re
   ETH_ADDRESS_REGEX = re.compile(r"^0x[0-9a-fA-F]{40}$")

   if account:
       if not isinstance(account, str) or not ETH_ADDRESS_REGEX.match(account):
           raise HTTPException(status_code=400, detail="Invalid Ethereum address format")
       app.state.bridge_server.set_connected_account(account)
   ```

3. **Chain ID Sanitization & EIP-155 Positive Integer Enforcement**:
   Catch `(ValueError, TypeError, Exception)` and enforce `cid > 0`:
   ```python
   if chain_id is not None:
       try:
           if isinstance(chain_id, (int, str)):
               cid = int(str(chain_id), 16) if str(chain_id).startswith("0x") else int(chain_id)
               if cid > 0:
                   app.state.bridge_server.chain_id = cid
               else:
                   raise HTTPException(status_code=400, detail="Chain ID must be a positive integer")
           else:
               raise HTTPException(status_code=400, detail="Invalid chain_id format")
       except (ValueError, TypeError):
           raise HTTPException(status_code=400, detail="Invalid chain_id format")
   ```
   Apply the identical `(ValueError, TypeError)` and `cid > 0` guard to `json_rpc_proxy` (`visualization/server/app.py:216–220`).

---

## 5. Verification Method

To independently reproduce all empirical observations and verify when the fixes are applied:

1. **Execute the Dedicated Adversarial Stress Harness**:
   ```powershell
   python tests/adversarial/test_m6_live_endpoint_stress.py
   ```
   *Current Observation*:
   - 39 / 44 tests PASS (Auth Gate, Rate Limiter 30-burst, WebSocket concurrency/heartbeat).
   - 5 / 44 tests FAIL on `TestEmpiricalPayloadAndValidationVulnerabilities`:
     - `test_vulnerability_wallet_sync_non_dict_payload_crash` (crashes with 500)
     - `test_vulnerability_wallet_sync_non_scalar_chain_id_crash` (crashes with 500)
     - `test_vulnerability_rpc_non_scalar_chain_id_crash` (crashes with 500)
     - `test_vulnerability_non_hex_account_accepted_without_validation` (status 200 instead of 400)
     - `test_vulnerability_negative_chain_id_accepted_without_validation` (status 200 instead of 400)

2. **Execute Existing Verification & Regression Harnesses**:
   ```powershell
   python tests/verify_live_terminal_metamask.py
   python -m pytest tests/unit -v
   python tests/e2e/run_all.py
   ```
   *Current Output*: All existing baseline tests pass (8/8 in live harness, 102/102 unit, 200/200 e2e).

3. **Remediation Acceptance Condition**:
   Once the worker applies the specified input guards in `visualization/server/app.py`:
   - Running `python tests/adversarial/test_m6_live_endpoint_stress.py` must result in **44 passed, 0 failed**.
   - No 500 errors on malformed payloads.
   - Non-hex addresses and negative chain IDs rejected with HTTP 400.
