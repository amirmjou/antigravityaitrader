# Handoff Report: Terminal Service & MetaMask Bridge Infrastructure (Requirement R1)

**Agent**: `teamwork_explorer_metamask_live_1`  
**Role**: Terminal Service Explorer  
**Task**: Survey codebase for Requirement R1 (Live Terminal and MetaMask Bridge Service)  
**Date**: 2026-11-08T23:12:00Z  
**Recipient**: `56b3c564-3f59-4841-ab4a-c6a6e410c34a` (Orchestrator)

---

## 1. Observation

### 1.1 Existing Terminal Entry Point (`run_live_metamask_terminal.py`)
- **File Path**: `c:\Users\AmirM\Documents\Agentic trading\run_live_metamask_terminal.py` (212 lines)
- **Token Configuration (Line 40)**:
  ```python
  LIVE_SESSION_TOKEN = os.environ.get("TRADING_API_KEY", "ag_live_metamask_2026_token")
  ```
- **App Factory & Security Mode (Lines 192–201)**:
  ```python
  def build_live_app():
      os.environ["TRADINGAGENTS_SECURITY_MODE"] = "production"
      os.environ["TRADING_API_KEY"] = LIVE_SESSION_TOKEN
      app = create_visualization_app()

      @app.on_event("startup")
      async def _start_live_loop():
          asyncio.create_task(live_market_and_ai_trading_loop(app))

      return app
  ```
- **Launcher Execution (Lines 204–212)**:
  ```python
  if __name__ == "__main__":
      print("================================================================================")
      print(" ANTIGRAVITY LIVE AI TRADING TERMINAL + METAMASK EIP-1193 BRIDGE")
      print("================================================================================")
      print(f" Security Mode:      PRODUCTION (Token Auth Enforced)")
      print(f" Live Terminal URL:  http://localhost:8899/?token={LIVE_SESSION_TOKEN}")
      print("================================================================================")
      uvicorn.run(build_live_app(), host="127.0.0.1", port=8899, log_level="info")
  ```
- **Verification Tool Command & Result**:
  Command:
  `python -c "import run_live_metamask_terminal; print('Import OK'); app = run_live_metamask_terminal.build_live_app(); print('App type:', type(app))"`
  Result:
  `Import OK`
  `App type: <class 'fastapi.applications.FastAPI'>`

---

### 1.2 Web Visualization Server & Auth Enforcement

- **File Path**: `c:\Users\AmirM\Documents\Agentic trading\visualization\server\app.py` (304 lines)
- **Static Assets & Templates Resolution (Lines 61–65)**:
  ```python
  base_dir = Path(__file__).resolve().parent.parent / "web"
  s_dir = static_dir or (base_dir / "static")
  t_dir = templates_dir or (base_dir / "templates")
  ```
  Static files exist at `visualization/web/static/` (CSS at `dashboard.css`, JS at `app.js` and `chart_engine.js`).
  Templates exist at `visualization/web/templates/index.html`.
- **Existing Dashboard Route (Lines 293–301)**:
  ```python
  # Serve dashboard root and fallback
  index_path = t_dir / "index.html"

  @app.get("/", response_class=HTMLResponse)
  @app.get("/dashboard", response_class=HTMLResponse)
  async def get_dashboard():
      if index_path.exists():
          return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)
      return HTMLResponse(
          content="<!DOCTYPE html><html><head><title>Antigravity Terminal</title></head><body><h1>Antigravity Trading Visualization</h1></body></html>",
          status_code=200,
      )
  ```
- **Security Dependency in `visualization/server/security.py` (Lines 80–108)**:
  `verify_api_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme))`
  Checks Bearer token, `X-API-Key` header, or `?token=` query parameter.
  When `is_auth_enforced()` is true (in production mode or `TRADING_API_KEY` set), raises `HTTPException(status_code=401, detail="Unauthorized")` if the token is missing or does not match `TRADING_API_KEY` in constant time (`verify_token_string`).
  In development mode without API key, returns `"development_bypass"`.
- **Empirical Test of Current Behavior**:
  Command:
  `python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app); print('With token:', client.get('/?token=ag_live_metamask_2026_token').status_code); print('Without token:', client.get('/').status_code); print('Invalid token:', client.get('/?token=bad').status_code)"`
  Result:
  `With token: 200`
  `Without token: 200` (GAP: Does not return 401/403)
  `Invalid token: 200` (GAP: Does not return 401/403)

- **Frontend Client Token Handling**:
  `visualization/web/static/js/app.js` (lines 15–42) extracts `?token=` from `window.location.search`, persists it in `localStorage.setItem('TRADING_API_KEY', urlToken)`, and appends it to all subsequent requests (`/ws/telemetry?token=...`, `/events/reasoning?token=...`, and `/rpc` with Bearer auth).

---

### 1.3 MetaMask Bridge Routes & Account Sync
- **Current Bridge Registration in `visualization/server/app.py`**:
  - `POST /rpc` (lines 201–233): Protected with `_token: str = Depends(verify_api_token)`.
    Handles `method == "wallet_syncAccount"` (lines 210–226):
    Calls `app.state.bridge_server.set_connected_account(addr)`, sets chain ID, publishes execution trader event to hub, and returns `{"jsonrpc": "2.0", "id": rpc_req.id, "result": app.state.bridge_server.connected_accounts}`.
  - `POST /send-transaction` (lines 235–239): Protected with `_token: str = Depends(verify_api_token)`.
  - `POST /confirm-transaction` (lines 240–246): Protected with `_token: str = Depends(verify_api_token)`.
- **Observation on Acceptance Criteria**:
  Acceptance criteria states: *"The bridge endpoint `/wallet_syncAccount` (or `/rpc`) accepts wallet account sync requests and updates connected accounts."*
  Currently, `/wallet_syncAccount` is supported via `/rpc` JSON-RPC calls. A standalone route `POST /wallet_syncAccount` is not yet registered.

---

### 1.4 Windows PowerShell Daemon Execution & Operational Infrastructure
- **Port 8899 State**:
  Command: `Get-NetTCPConnection -LocalPort 8899 -ErrorAction SilentlyContinue`
  Result: Exit code 1, no active listener on port 8899.
- **Python Runtime & Packages**:
  Python 3.11.9 on win32.
  `psutil` v7.2.2 is installed and available for PID and port connection tracking.
- **Existing Test Suite Baseline**:
  - `tests\unit\test_visualization.py`: 33 passed in 6.46s
  - `tests\adversarial\test_security_hardening.py`: 32 passed in 7.35s
  - `tests\adversarial\test_m6_adversarial_challenge.py`: 68 passed in 7.21s

---

## 2. Logic Chain

1. **Step 1: Requirement Alignment for R1**
   - Requirement R1 states: *"Start and keep running the live trading bot terminal service (`run_live_metamask_terminal.py`) on `http://127.0.0.1:8899` with production security token authentication enabled, exposing the web visualization UI and MetaMask bridge."*
   - Acceptance Criteria #2: *"An HTTP GET request to `http://127.0.0.1:8899/?token=ag_live_metamask_2026_token` returns HTTP status 200 with the live trading visualization HTML."*
   - Acceptance Criteria #3: *"Requests without a valid authorization token or API key return HTTP status 401 or 403."*

2. **Step 2: Root Cause of Acceptance Criteria #3 Failure**
   - In `visualization/server/app.py:293–301`, `get_dashboard()` defines routes `GET /` and `GET /dashboard` without any dependency injection (`verify_api_token`).
   - Although `/rpc`, `/send-transaction`, `/events/reasoning`, and `/ws/telemetry` properly enforce `verify_api_token`, the HTML dashboard itself serves unauthenticated requests with HTTP 200.
   - When `_token: str = Depends(verify_api_token)` is injected into `get_dashboard(_token: str = Depends(verify_api_token))` in `app.py`:
     - Under `TRADINGAGENTS_SECURITY_MODE=production`:
       - `/?token=ag_live_metamask_2026_token` passes verification and returns HTTP 200.
       - Missing token or invalid token triggers `HTTPException(401, detail="Unauthorized")`.
     - Under default development mode (no env vars set):
       - `is_auth_enforced()` returns `False`, so `verify_api_token` returns `"development_bypass"` with HTTP 200, guaranteeing zero regressions for existing unit test suites (e.g. `test_root_serves_html_dashboard` in `test_visualization.py`).

3. **Step 3: Dual Compatibility for `/wallet_syncAccount`**
   - `visualization/web/static/js/app.js:451–460` sends `POST /rpc` with method `"wallet_syncAccount"`.
   - To fully satisfy acceptance criteria for tests or clients that call either `POST /rpc` or `POST /wallet_syncAccount` directly, a top-level route `POST /wallet_syncAccount` can be added to `app.py` that delegates to `app.state.bridge_server.set_connected_account(account)`.

4. **Step 4: Reliable Windows PowerShell Background Execution & Lifecycle**
   - On Windows, process collisions on port 8899 produce `OSError: [WinError 10048]`.
   - Pre-flight port verification can be performed using PowerShell:
     ```powershell
     $portProc = (Get-NetTCPConnection -LocalPort 8899 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1)
     if ($portProc) { Stop-Process -Id $portProc -Force }
     ```
   - Starting the background daemon reliably:
     - Via PowerShell:
       ```powershell
       $proc = Start-Process -FilePath "python" -ArgumentList "run_live_metamask_terminal.py" -PassThru -NoNewWindow
       $proc.Id | Out-File -FilePath ".live_terminal.pid" -Encoding ascii
       ```
     - Via Agent Tool: `run_command` with `CommandLine="python run_live_metamask_terminal.py", IsDaemon=true, WaitMsBeforeAsync=2000`.
   - Healthcheck Polling:
     - `GET http://127.0.0.1:8899/health` is deliberately public (unauthenticated) per `test_health_endpoints_remain_public` in `test_security_hardening.py:158`, making it the ideal healthcheck endpoint.
     - Polling loop checks HTTP status 200 and `"status": "ok"` within a 15-second timeout.
   - Clean Teardown:
     - PowerShell: `Stop-Process -Id (Get-Content .live_terminal.pid) -Force -ErrorAction SilentlyContinue; Remove-Item .live_terminal.pid -ErrorAction SilentlyContinue`
     - Optional token-authenticated management endpoint `POST /api/shutdown` can also be provided.

---

## 3. Caveats

1. **Static Files Accessibility**:
   `/static` assets (`dashboard.css`, `app.js`, `chart_engine.js`) are mounted via `StaticFiles(directory=str(s_dir))`. Static files do not have query-parameter token awareness. Keeping `/static` public while enforcing authentication on `GET /` and `GET /dashboard` is the standard and correct pattern (browsers request `/?token=...`, parse the HTML, and fetch static assets without token query strings).
2. **Third-Party Exchange Ticker Fallback**:
   `fetch_real_spot_price` in `run_live_metamask_terminal.py` attempts a 3-second REST query to Coinbase (`https://api.coinbase.com/v2/prices/BTC-USD/spot`). If network is unreachable or blocked, it gracefully falls back to synthetic Gaussian random walk anchored to $88,500.00. This ensures zero hangs or crashes in offline or air-gapped test environments.

---

## 4. Conclusion & Concrete Recommendations

### Summary of Findings
1. `run_live_metamask_terminal.py` is present, valid, and fully functional. It configures `TRADINGAGENTS_SECURITY_MODE=production` and `TRADING_API_KEY=ag_live_metamask_2026_token` on startup.
2. **Identified Gap**: `get_dashboard()` in `visualization/server/app.py:293–301` lacks `_token: str = Depends(verify_api_token)`. Adding this dependency is required to satisfy Acceptance Criteria #3 (rejecting unauthenticated requests with HTTP 401).
3. **Enhancement**: Register a direct `POST /wallet_syncAccount` route in `visualization/server/app.py` in addition to the existing JSON-RPC `/rpc` method to guarantee seamless interoperability.
4. **Daemon Management**: Windows PowerShell scripts and automated runners should use pre-flight port checks, `Start-Process` with PID file tracking (or `run_command` with `IsDaemon=true`), and poll `http://127.0.0.1:8899/health`.

### Proposed Code Changes (For Implementation Agent)

#### Change 1: Enforce Security Token on Dashboard Route
**Target File**: `visualization/server/app.py` (lines 293–301)
```python
<<<<
    # Serve dashboard root and fallback
    index_path = t_dir / "index.html"

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard():
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)
        return HTMLResponse(
            content="<!DOCTYPE html><html><head><title>Antigravity Terminal</title></head><body><h1>Antigravity Trading Visualization</h1></body></html>",
            status_code=200,
        )
====
    # Serve dashboard root and fallback (enforces security token in production mode)
    index_path = t_dir / "index.html"

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard(_token: str = Depends(verify_api_token)):
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)
        return HTMLResponse(
            content="<!DOCTYPE html><html><head><title>Antigravity Terminal</title></head><body><h1>Antigravity Trading Visualization</h1></body></html>",
            status_code=200,
        )
>>>>
```

#### Change 2: Register Direct `/wallet_syncAccount` Endpoint
**Target File**: `visualization/server/app.py` (around line 234)
```python
    @app.post("/wallet_syncAccount", dependencies=[Depends(rate_limit_dependency(max_requests=30, category="rpc"))])
    async def direct_wallet_sync_account(request: Request, _token: str = Depends(verify_api_token)):
        """Direct REST endpoint for MetaMask account synchronization."""
        body = await request.json()
        account = body.get("account") or (body.get("params")[0] if isinstance(body.get("params"), list) and body.get("params") else None)
        chain_id = body.get("chain_id") or (body.get("params")[1] if isinstance(body.get("params"), list) and len(body.get("params")) > 1 else None)
        if account:
            app.state.bridge_server.set_connected_account(account)
            if chain_id:
                try:
                    cid = int(str(chain_id), 16) if str(chain_id).startswith("0x") else int(chain_id)
                    app.state.bridge_server.chain_id = cid
                except ValueError:
                    pass
            app.state.telemetry_hub.publish_event(
                "agent_thought",
                "Execution Trader",
                f"MetaMask Wallet Connected: {account} (Chain ID: {app.state.bridge_server.chain_id}) — Live On-Chain Execution Armed.",
            )
        return {
            "status": "synchronized",
            "connected_accounts": app.state.bridge_server.connected_accounts,
            "chain_id": app.state.bridge_server.chain_id,
        }
```

---

## 5. Verification Method

To independently verify these findings:

1. **Verify Root Dashboard Auth Behavior (Pre-fix vs Post-fix)**:
   ```powershell
   python -c "from starlette.testclient import TestClient; import run_live_metamask_terminal; app = run_live_metamask_terminal.build_live_app(); client = TestClient(app); print('With valid token:', client.get('/?token=ag_live_metamask_2026_token').status_code); print('Without token:', client.get('/').status_code); print('With invalid token:', client.get('/?token=wrong').status_code)"
   ```
   - Current output: `200`, `200`, `200` (exposes gap).
   - Expected output after proposed change: `200`, `401`, `401`.

2. **Verify Regression Safety across Existing Test Suites**:
   ```powershell
   python -m pytest tests/unit/test_visualization.py -v
   python -m pytest tests/adversarial/test_security_hardening.py -v
   python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v
   ```

3. **Verify Terminal Startup on Port 8899 & Healthcheck**:
   ```powershell
   # Check port 8899 is free
   Get-NetTCPConnection -LocalPort 8899 -ErrorAction SilentlyContinue

   # Test healthcheck response
   python -c "import urllib.request, json; print(json.loads(urllib.request.urlopen('http://127.0.0.1:8899/health').read().decode()))"
   ```

4. **Invalidation Conditions**:
   - If `test_root_serves_html_dashboard` fails in dev mode, check that `is_auth_enforced()` continues to bypass when `TRADINGAGENTS_SECURITY_MODE` and `TRADING_API_KEY` are unset.
   - If port 8899 reports `WinError 10048`, ensure previous python processes are cleared using `Stop-Process`.
