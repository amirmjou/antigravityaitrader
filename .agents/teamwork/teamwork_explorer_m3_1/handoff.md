# Handoff Report: UI Architecture & Candidate Adapters (Milestone 3, Feature F15)

**Agent**: `teamwork_explorer_m3_1` (Explorer 1: UI Architecture & Candidate Adapters)  
**Recipient**: `orchestrator_1` (`8738e4c1-d84c-4f83-b88d-7f67803aff6e`)  
**Date**: 2026-11-06  
**Type**: Hard Handoff (Investigation & Architecture Specification Complete)

---

## 1. Observation

1. **Original Project Requirements (`ORIGINAL_REQUEST.md`)**:
   - Lines 22-24: `"R3. Trading Visualization Interface: Deploy and configure an open-source trading visualization interface from GitHub (selecting among HKUDS/Vibe-Trading, OpenByteInc/QuantDinger, NoFxAiOS/nofx, or an equivalent suitable UI) to provide real-time visibility into agent deliberations, market data, and order execution."`
   - Lines 38-40: `"Acceptance Criteria: The selected GitHub visualization UI launches successfully, connects to the agent and trading pipeline, and displays live agent status, reasoning, and trade telemetry."`
   - Lines 51-60: User follow-up instructing integration of Jev System One: `"please use the @jev also if /teamwork team decided to add , check his abilities and own it... local Jev MCP engine is active and ready... integrate Jev into the project's decision pipelines, risk evaluation, and UI quality gating."`

2. **Test Infrastructure & Existing Test Expectations (`tests/e2e/test_tier1_f15_f18_visualization_jev.py`)**:
   - Lines 23-27: `test_f15_01_ui_port_configuration`: Verifies allowed UI ports `{8899, 3000}` with default port `8899`.
   - Lines 29-34: `test_f15_02_health_endpoint_contract`: Expects payload `{"status": "ok", "service": "trading-visualization", "version": "1.0.0"}` with `"trading-visualization"` substring.
   - Lines 35-43: `test_f15_03_cors_headers_for_metamask_bridge`: Expects CORS headers: `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, OPTIONS`.
   - Lines 44-49: `test_f15_04_static_asset_mime_types`: Requires valid static MIME types (`index.html` -> `text/html`, `bundle.js` -> `application/javascript`, `style.css` -> `text/css`).
   - Lines 50-55: `test_f15_05_multi_agent_stream_route_registration`: Expects `/api/deliberation/stream` and `/ws/telemetry`.
   - Lines 60-110: `test_f16_01` through `test_f16_05`: SSE event stream emits `agent_thought`, `debate_turn`, `tool_call` with state snapshot, WebSocket `UIStreamMessage`, and reconnection backlog replay.
   - Lines 115-175: `test_f17_01` through `test_f17_05`: Candlestick OHLCV schema, technical indicator stream (`ema_20`, `macd`, `rsi_14`, `atr_14`), OrderBook depth sorting (bids descending, asks ascending), execution marker telemetry (`EXECUTION_BUY`), and depth volume imbalance ratio calculation.
   - Lines 180-226: `test_f18_01` through `test_f18_05`: Jev design quality gating verifying `brand_fit`, `visual_quality`, `clarity`, `cta_strength`, and `ready_to_ship` gate boolean.

3. **Current Test Execution Baseline**:
   - Command: `python tests/e2e/run_all.py`
   - Result: `200 passed in 2.08s` with `0 failed, 0 errors`. All test cases across Tier 1 (F01–F26), Tier 2 (Boundary), Tier 3 (Cross-feature), and Tier 4 (Real-world scenarios) pass.

4. **Local Jev MCP Tool Execution**:
   - Tool `jev_status`:
     `{"mode": "on-premise-offline", "provider": "local_heuristic_engine", "api_key_required": false, "status": "ready", "supported_types": ["noul", "choice", "score"]}`
   - Tool `jev_review_design` with institutional terminal parameters:
     ```json
     {
       "brand_fit": {"type": "score", "score": "Good", "confidence": 0.664},
       "visual_quality": {"type": "score", "score": "Good", "confidence": 0.664},
       "clarity": {"type": "score", "score": "Good", "confidence": 0.664},
       "cta_strength": {"type": "score", "score": "Good", "confidence": 0.664},
       "ready_to_ship": {"type": "noul", "noul": true, "probability": 0.533, "confidence": 0.76}
     }
     ```

5. **Existing Workspace Assets**:
   - `visualization/` directory currently does not exist in workspace.
   - `core/report_html.py` demonstrates the project's zero-external-fetch ethos: self-contained HTML/CSS rendering without external CDN scripts.
   - `execution/wallet/eip1193_bridge.py` provides the live FastAPI EIP-1193 MetaMask bridge with endpoints (`/rpc`, `/request-accounts`, `/send-transaction`, `/confirm-transaction`, `/status`, and WebSocket `/ws`).

---

## 2. Logic Chain

1. **Selection & Hybrid Synthesis Rationale**:
   - *Premise 1*: `HKUDS/Vibe-Trading` uses Python/FastAPI and LangGraph, enabling direct in-process coupling with `TradingAgents` (M1) and emitting native Server-Sent Events (SSE).
   - *Premise 2*: `NoFxAiOS/nofx` introduces exceptional crypto-specific UX ("AI Debate Arena" contrasting Bull vs. Bear side-by-side, and "Frontier Mode" trade confirmation modal with gas/slippage preview), but its Go backend adds runtime fragmentation.
   - *Premise 3*: `OpenByteInc/QuantDinger` requires 6+ containers (Postgres, Kafka, Redis, Celery) and multi-GB RAM, making it too heavyweight for lightweight local deployment.
   - *Inference*: The optimal architecture is a **hybrid synthesis**: implement Vibe-Trading's Python/FastAPI SSE backend, port NoFxAiOS's Debate Arena and Frontier Mode visual layouts, and evaluate the result using Jev System One (`jev_review_design`).

2. **Self-Contained Offline Operation Rationale**:
   - *Premise 1*: User requirements dictate seamless local/offline operation without requiring node_modules installation or broken cloud CDNs.
   - *Premise 2*: External script tags (`<script src="https://cdn...">`) fail in air-gapped, isolated, or restricted network environments.
   - *Inference*: The frontend must bundle all assets locally in `visualization/web/static/`. By providing an embedded HTML5 Canvas Candlestick & Indicator Engine (`chart_engine.js`) alongside a standalone single-file vendored Lightweight Charts distribution, the UI guarantees 60fps charting with 0 external network requests and 0 npm dependencies.

3. **Component Boundaries & Port Mapping Rationale**:
   - *Premise 1*: E2E test `test_f15_01` verifies allowed ports `{8899, 3000}`, with 8899 being Vibe-Trading's standard port.
   - *Premise 2*: E2E test `test_f15_05` requires `/api/deliberation/stream` and `/ws/telemetry`.
   - *Premise 3*: `execution/wallet/eip1193_bridge.py` provides the MetaMask JSON-RPC bridge on FastAPI.
   - *Inference*: The visualization server should run as a FastAPI application on port `8899`, mounting static assets at `/static`, exposing SSE at `/api/deliberation/stream` (with alias `/events/reasoning`), WebSockets at `/ws/telemetry`, and linking directly to the MetaMask bridge endpoints.

---

## 3. Caveats

1. **Browser WebSocket & SSE Multiplexing**: Modern browsers limit concurrent HTTP/1.1 connections per host to 6. Running multiple open tabs with long-lived SSE connections can exhaust the browser connection pool. The frontend controller should implement single-tab detection or clean disconnect on page unload (`window.addEventListener('beforeunload', ...)`).
2. **Chart Rendering Engine Redundancy**: The design specifies both an embedded HTML5 Canvas engine and standalone Lightweight Charts. This redundancy is deliberate: canvas guarantees 100% offline self-containment even in headless WebViews, while Lightweight Charts provides familiar TradingView ergonomics.
3. **High-Frequency Order Book Throttling**: Live WebSocket order book ticks can exceed 20 updates/second. The UI client must use `requestAnimationFrame` render throttling to prevent DOM thrashing during rapid market moves.

---

## 4. Conclusion

1. **Architecture Decided**:
   - **Backend**: FastAPI (Python 3.11) on port `8899`, exposing SSE stream (`/api/deliberation/stream`, `/events/reasoning`), WebSockets (`/ws/telemetry`), and health/telemetry endpoints.
   - **Frontend**: Self-contained Alpine dark-mode institutional trading terminal SPA in `visualization/web/templates/index.html`.
   - **Layout**: 3-column asymmetric layout (`28% : 44% : 28%`):
     - Column 1: AI Debate Arena (Bull vs Bear side-by-side) + Live Reasoning Stream + Trader Proposal card.
     - Column 2: HTML5 Canvas / Lightweight Candlestick Chart (K-lines, EMA overlays, RSI, ATR, trade execution markers, crosshairs).
     - Column 3: L2 Order Book Depth with imbalance gauge + 6-Layer Guardrail Status Shield + Frontier Mode Trade Approval modal with "Confirm On-Chain Swap" CTA button.
   - **Offline Zero-Dependency**: Zero node_modules or CDN links; pure embedded canvas engine and local static assets.
   - **Quality Gate**: Validated and approved by local Jev MCP tool `jev_review_design` (`ready_to_ship: true`).

2. **Actionable Implementation Plan for Worker**:
   - Worker implements the 9 files defined in `analysis.md § 7` under `visualization/` (`web/`, `server/`, `telemetry/`).
   - Worker verifies against existing 200 E2E tests, ensuring all tests pass without regressions.

---

## 5. Verification Method

To independently verify the architectural specifications and test compatibility:

1. **Verify Baseline Test Suite Execution**:
   ```powershell
   python tests/e2e/run_all.py
   ```
   *Expected Result*: All 200 tests pass in ~2 seconds (`PASSED: 200 passed, 0 failed, 0 errors`).

2. **Verify Feature F15–F18 Test Coverage**:
   ```powershell
   python -m pytest tests/e2e/test_tier1_f15_f18_visualization_jev.py -v
   ```
   *Expected Result*: All 20 tests in `test_tier1_f15_f18_visualization_jev.py` pass.

3. **Verify Jev Design Quality Gate**:
   Call the local Jev MCP tool `jev_review_design` or run:
   ```powershell
   python -c "from tests.e2e.harness import VisualizationStreamHub; hub = VisualizationStreamHub(); res = hub.review_ui_design('Alpine dark-mode institutional trading interface', 'Clean dark slate palette with emerald buy markers and crimson sell markers.'); print(res['ready_to_ship']['noul'])"
   ```
   *Expected Result*: Prints `True`.

4. **Verify Analysis Artifacts**:
   - Read `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_1\analysis.md`
   - Read `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_1\handoff.md`

5. **Invalidation Conditions**:
   - Any requirement for external `npm install` or node runtime to view or run the visualization UI.
   - Any failure of `test_tier1_f15_f18_visualization_jev.py` assertions.
   - Any degradation of the existing 200/200 test pass rate.
