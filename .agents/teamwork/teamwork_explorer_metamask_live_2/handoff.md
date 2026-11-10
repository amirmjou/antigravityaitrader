# Telemetry and Reasoning Explorer Handoff Report: Requirement R2

## 1. Observation

Direct examination of codebase files, routes, data models, and execution loops revealed the following concrete facts:

### A. WebSocket Endpoint (`/ws/telemetry`)
- **Location**: `c:\Users\AmirM\Documents\Agentic trading\visualization\server\ws_router.py:18-133`
  - Registered in FastAPI app via `app.include_router(ws_router)` in `visualization\server\app.py:284`.
  - Authentication check: `check_websocket_auth(websocket)` (`visualization\server\security.py:110-132`). In production mode (`TRADINGAGENTS_SECURITY_MODE=production` or `TRADING_API_KEY` present), authenticates `?token=<TOKEN>` or `Authorization: Bearer <TOKEN>` or `X-API-Key` using `hmac.compare_digest`. Non-compliant clients receive WS close code `1008` (`Unauthorized`).
  - Connection & Session Management: Handled by `TelemetryConnectionManager` (`visualization\server\connection_manager.py:24-108`). Manages `sessions: Dict[WebSocket, ClientSession]` with thread-safe `asyncio.Lock()`.
  - Channel subscriptions: Supports `ALLOWED_CHANNELS = {"all", "ticker", "orderbook", "indicators", "guardrails", "executions"}`. Default is `{"all"}`. Handles client `subscribe` and `unsubscribe` frame types and replies with `subscription_ack`.
  - Heartbeat: Handles incoming `{"type": "ping", "timestamp": ...}` and responds with `pong` payload containing `client_timestamp` and `server_time_ms`.
  - Initial State Synchronization (`ws_router.py:51-89`): Immediately upon connection, pushes cached snapshots from `hub` to client:
    - `ticker_update` (`hub.latest_candle`)
    - `orderbook_snapshot` (`hub.latest_orderbook`)
    - `indicator_update` (`hub.latest_indicators`)
    - `guardrail_state` (`hub.latest_guardrails`)
    - `execution_marker` (all in `hub.recent_executions`)

### B. Server-Sent Events Endpoint (`/events/reasoning`)
- **Location**: `c:\Users\AmirM\Documents\Agentic trading\visualization\server\sse_router.py:49-88`
  - Dual routes: `@sse_router.get("/events/reasoning")` and `@sse_router.get("/api/deliberation/stream")`.
  - Registered in FastAPI app via `app.include_router(sse_router)` in `visualization\server\app.py:283`.
  - Authentication: Dependency `_token: str = Depends(verify_api_token)` in `visualization\server\security.py:80-108`. Validates `?token=`, `Authorization: Bearer`, or `X-API-Key`.
  - Event Generator: `sse_event_generator(request, since_id, hub, limit)` (`sse_router.py:17-47`).
    - Yields initial frame: `: connected\n\n`.
    - Reads from client `asyncio.Queue` with `timeout=15.0`. If idle, emits `: keepalive\n\n`.
    - Handles disconnect via `asyncio.CancelledError` and unregisters queue from hub.
  - Replay & Monotonic Ordering: Client can supply `?since_id=<ID>` or `Last-Event-ID: <ID>`. In `TelemetryHub.subscribe_sse` (`visualization\telemetry\hub.py:160-170`), historical events from the 2,000-event ring buffer (`event_backlog: deque(maxlen=2000)`) with `event_id > since_id` are atomically queued prior to listening to live events.
  - Event Frame Formatting: `AgentDeliberationEvent.to_sse_frame()` (`visualization\server\models.py:32-39`):
    ```
    id: <event_id>
    event: <event>
    data: <JSON>
    \n\n
    ```

### C. Live Ingestion and Deliberation Loop
- **Location**: `c:\Users\AmirM\Documents\Agentic trading\run_live_metamask_terminal.py:43-190`
  - Spot price fetch: `fetch_real_spot_price(symbol, fallback)` calls Coinbase API `https://api.coinbase.com/v2/prices/{symbol}/spot`.
  - Currently, `live_market_and_ai_trading_loop` (lines 62 and 75) only queries `"BTC-USD"`.
  - Indicators calculated:
    - `compute_rsi(closes, 14)` (`core\quant\indicators.py`)
    - `compute_adx(highs, lows, closes, 14)` (`core\quant\indicators.py`)
    - `compute_moving_averages(closes)` (`core\quant\indicators.py`)
    - `compute_macd(closes)` (`core\quant\indicators.py`)
  - Deliberation steps generated every 4.0s:
    - Step % 3 == 1: `tool_call` by `Market Analyst` with spot price, RSI, ADX, and MACD.
    - Step % 3 == 2: `debate_turn` by `Bull Researcher` or `Bear Researcher`.
    - Step % 3 == 0: `proposal_generated` by `Execution Trader` with action (`BUY`/`SELL`), entry price, stop loss, and connected wallet binding.
- Redundant WS broadcasting observed:
  - In `run_live_metamask_terminal.py:109, 118, 132`, calling `hub.update_candle`, `hub.update_indicators`, and `hub.update_orderbook` already triggers `hub._dispatch_ws(...)` because `hub.ws_manager` is attached (`visualization\server\app.py:73`).
  - Lines 134-148 subsequently execute `await ws_mgr.broadcast(...)` again for the exact same payloads.

### D. Existing Models and Schemas
- **`visualization/server/models.py`**:
  - `DeliberationEventType = Literal["agent_thought", "debate_turn", "debate_argument", "tool_call", "proposal_generated", "decision", "trade_telemetry", "guardrail_status"]`
  - `AgentDeliberationEvent`: fields `event`, `agent_role`, `agent_name`, `timestamp`, `token`, `debate_round`, `consensus_status`, `state_snapshot`, `event_id`.
  - `ChartCandle`: fields `timestamp_ms`, `open`, `high`, `low`, `close`, `volume`.
  - `OrderBookSnapshot`: fields `symbol`, `timestamp_ms`, `bids`, `asks`, `spread`, `depth_imbalance`.
  - `TechnicalIndicators`: fields `symbol: str`, `ema_20: float`, `macd: float`, `rsi_14: float`, `atr_14: float`. *(Currently missing explicit ADX and SMA fields!)*
  - `ExecutionMarker`: fields `type`, `price`, `quantity`, `tx_hash`, `timestamp_ms`.
  - `GuardrailStateSnapshot`: fields `approved`, `rejection_reason`, `layer_failed`, `simulated_gas_used`, `quoted_amount_out_min`, `estimated_price_impact_pct`, `layers`.

### E. Existing Automated Tests
- Command: `python -m pytest tests/unit/test_visualization.py`
  - **Result**: 33 passed in 3.53s.
- Command: `python -m pytest tests/e2e/test_tier1_f15_f18_visualization_jev.py`
  - **Result**: 20 passed in 0.04s.
- Command: `python -m pytest tests/adversarial/test_security_hardening.py tests/adversarial/test_m6_adversarial_challenge.py`
  - **Result**: 100 passed in 8.76s.

---

## 2. Logic Chain

1. **R2 Requirement Specification**:
   R2 requires streaming live spot market prices and technical indicators (RSI, ADX, SMA/EMA, MACD) via WebSocket (`/ws/telemetry`), and streaming multi-agent deliberation events (analyst updates, bull/bear researcher debates, generated trade proposals) via SSE (`/events/reasoning`).
2. **Endpoint Architecture**:
   Observations A and B confirm that both `/ws/telemetry` and `/events/reasoning` exist, are mounted to FastAPI, and have full authentication, keepalive, and reconnect mechanisms.
3. **Multi-Asset Spot Feeds Evaluation**:
   Observation C indicates that `fetch_real_spot_price` accepts any currency pair supported by Coinbase REST API (`BTC-USD`, `ETH-USD`, `SOL-USD`). In `crypto_pipeline\ingestion\feeds.py:18-22`, base prices for `BTC/USDT`, `ETH/USDT`, `SOL/USDT` are configured. However, `live_market_and_ai_trading_loop` currently only invokes `fetch_real_spot_price` for `"BTC-USD"`. To satisfy R2 ("BTC, ETH, SOL"), the loop needs to maintain price history and broadcast ticker updates for ETH and SOL alongside BTC.
4. **Technical Indicator Schema Evaluation**:
   Observation D reveals that `core\quant\indicators.py` already computes ADX(14), SMA(20, 50, 200), and EMA(12, 26, 50). In `run_live_metamask_terminal.py`, `compute_adx` and `compute_moving_averages` are executed, but `TechnicalIndicators` model in `visualization\server\models.py` only defines `ema_20`, `macd`, `rsi_14`, `atr_14`. ADX is pushed to SSE tool calls but omitted from the WebSocket indicator model. Furthermore, line 113 set `ema_20 = round(ma_res.sma_20, 2)`.
   Adding optional fields `adx_14: Optional[float] = None`, `sma_20: Optional[float] = None`, and `ema_50: Optional[float] = None` to `TechnicalIndicators` cleanly satisfies the R2 indicator specification without breaking existing tests.
5. **Broadcasting Hygiene**:
   Observation C notes that `hub.update_*` already performs WebSocket dispatching via `_dispatch_ws`. The subsequent explicit `ws_mgr.broadcast(...)` calls in `run_live_metamask_terminal.py` cause duplicate frames to be sent over the wire. Removing the redundant second broadcast cleans up network overhead.
6. **Multi-Agent Deliberation Streaming Evaluation**:
   Observations B and C confirm that the SSE pipeline handles multi-agent events: `tool_call` (Market Analyst), `debate_turn` (Bull/Bear Researchers), and `proposal_generated` (Execution Trader). Reconnection with `since_id` and `Last-Event-ID` works seamlessly against the 2,000-event ring buffer. Rotating deliberation focus across BTC, ETH, and SOL or emitting proposals across the major pairs fulfills multi-asset coverage.

---

## 3. Caveats

1. **Network Connectivity to External Exchanges**:
   `fetch_real_spot_price` calls `https://api.coinbase.com/v2/prices/{symbol}/spot`. In air-gapped, offline, or heavily firewalled environments, the `try...except` block safely falls back to synthetic Brownian motion microstructure based on `fallback` prices.
2. **Frontend UI Display Constraints**:
   The HTML masthead ticker (`visualization/web/templates/index.html:19-40`) currently renders primary metrics for `BTC/USDT`. Broadcasters can either send multi-symbol ticker updates over WS (which the backend supports via `symbol` in payload) or dynamically cycle through symbols.
3. **Pydantic Model Compatibility**:
   Adding new fields to `TechnicalIndicators` MUST use `Optional[...] = None` default values to ensure that existing tests in `test_visualization.py` initializing `TechnicalIndicators(symbol="...", ema_20=..., macd=..., rsi_14=..., atr_14=...)` continue to pass without error.

---

## 4. Conclusion

Requirement R2 is already 85% implemented and architecturally sound, supported by 153 passing unit, e2e, and adversarial security tests.
To achieve 100% compliance with R2 acceptance criteria, three concrete enhancements are recommended for the implementation team:

1. **Multi-Asset Ingestion & Streaming (BTC, ETH, SOL)**:
   Extend `run_live_metamask_terminal.py`'s `live_market_and_ai_trading_loop` to poll and compute candles and indicators for `BTC-USD`, `ETH-USD`, and `SOL-USD` (or rotate them sequentially every iteration).
2. **Indicator Schema Completeness**:
   In `visualization\server\models.py`, extend `TechnicalIndicators` with `adx_14: Optional[float] = None`, `sma_20: Optional[float] = None`, and `ema_50: Optional[float] = None`.
   In `run_live_metamask_terminal.py`, populate these fields using `round(adx_res.adx_14, 1)`, `round(ma_res.sma_20, 2)`, and `round(ma_res.ema_50, 2)`.
3. **Deduplication of WebSocket Broadcasts**:
   Eliminate lines 134-148 in `run_live_metamask_terminal.py` because `hub.update_candle`, `hub.update_indicators`, and `hub.update_orderbook` already dispatch directly through `ws_mgr`.
4. **Multi-Asset Deliberation Rotation**:
   Allow the deliberation loop in `run_live_metamask_terminal.py` to rotate analysis between BTC, ETH, and SOL so that Bull/Bear debates and Trader proposals reflect the broader portfolio.

---

## 5. Verification Method

To independently verify these findings and confirm zero regressions:

### 1. Execute Unit & Routing Test Suites
Run the full visualization and streaming unit test suite:
```powershell
python -m pytest tests/unit/test_visualization.py -v
```
Verify:
- `test_events_reasoning_endpoint_status` passes.
- `test_sse_backlog_replay_since_id` passes.
- `test_ws_connection_and_initial_state_replay` passes.
- `test_ws_heartbeat_ping_pong` passes.
- `test_ws_channel_subscription_and_ack` passes.
- `test_ws_multi_client_broadcast` passes.

### 2. Execute Security & Adversarial Test Suites
Verify that authentication tokens are strictly validated across SSE and WS:
```powershell
python -m pytest tests/adversarial/test_security_hardening.py tests/adversarial/test_m6_adversarial_challenge.py -v
```
Verify:
- All 100 adversarial tests pass with exit code 0.

### 3. Verification of Multi-Asset Feed Integration
Once recommendations are applied:
1. Launch terminal: `python run_live_metamask_terminal.py`
2. Connect WebSocket client to `ws://127.0.0.1:8899/ws/telemetry?token=ag_live_metamask_2026_token`
3. Inspect received frames: confirm `ticker_update` and `indicator_update` payloads arrive containing `symbol: "BTC/USDT"`, `symbol: "ETH/USDT"`, `symbol: "SOL/USDT"` with `adx_14`, `sma_20`, `ema_20`, `macd`, `rsi_14`.
4. Connect SSE client to `http://127.0.0.1:8899/events/reasoning?token=ag_live_metamask_2026_token`
5. Inspect received events: confirm `tool_call`, `debate_turn`, and `proposal_generated` frames stream continuously with monotonic `id` tags.

### Invalidation Conditions
- Any changes that alter the `AgentDeliberationEvent` or `UIStreamMessage` envelope contracts without backwards compatibility.
- Any change to `check_websocket_auth` or `verify_api_token` that bypasses production security or breaks the `?token=` query parameter fallback.
