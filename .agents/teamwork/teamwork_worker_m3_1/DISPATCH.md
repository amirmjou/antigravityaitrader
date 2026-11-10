# Dispatch Assignment: Milestone 3 Implementation Worker

## Mission
Implement Milestone 3: Trading Visualization Interface (Features F15–F18) delivering an open-source trading dashboard with dual-channel SSE reasoning streaming, WebSocket telemetry, interactive charting, and automated Jev design quality gating (`jev_review_design`).

## 🔒 Mandatory Integrity Warning
> DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Mandatory Context
Read `ORIGINAL_REQUEST.md` verbatim (including the user follow-up regarding @jev):
`c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md`

Read `PROJECT.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\PROJECT.md`

Read `TEST_INFRA.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\TEST_INFRA.md`

## Input Evidence & Explorer Specifications
Study the comprehensive analysis and handoff reports prepared by the 3 Milestone 3 Explorers:
1. **UI Architecture & Candidate Adapters**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_1\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_1\handoff.md`
2. **Streaming Telemetry & Real-Time Events**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_2\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_2\handoff.md`
3. **Jev Design Review Gate & UI Validation**:
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_3\analysis.md`
   - `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_3\handoff.md`

## Implementation Tasks

### Task 1: Core Telemetry Engine (`visualization/telemetry/`)
- `visualization/telemetry/hub.py`:
  - `TelemetryHub` with thread-safe 2,000-event ring buffer.
  - Event schemas: `agent_thought`, `debate_argument`, `tool_call`, `proposal_generated`, `decision`, `trade_telemetry`, `guardrail_status`.
  - Reconnection support via `since_id` and `Last-Event-ID`.
- `visualization/telemetry/callbacks.py`:
  - `ReasoningStreamCallbackHandler` integrating LangGraph / LangChain agent LLM streaming and debate arguments into `TelemetryHub`.

### Task 2: FastAPI Streaming Server (`visualization/server/`)
- `visualization/server/app.py`:
  - FastAPI application mounted on port 8899 (or configurable).
  - Mount `/static` to `visualization/web/static`.
  - Mount `/` to serve `visualization/web/templates/index.html`.
  - Integrate with `execution/wallet/eip1193_bridge.py` for live MetaMask wallet connectivity.
- `visualization/server/sse_router.py`:
  - Dual SSE endpoints: `/events/reasoning` and `/api/deliberation/stream`.
  - 15s keepalive ping frames (`: keepalive\n\n`).
- `visualization/server/ws_router.py`:
  - WebSocket endpoint `/ws/telemetry` with `TelemetryConnectionManager`.
  - Full-duplex messaging: K-lines/OHLCV, sorted order book depth, indicators (EMA 20/50, RSI 14, ATR 14), trade execution markers, active guardrail shield state.
  - Heartbeat ping/pong (`{"type": "ping"}` -> `{"type": "pong"}`).

### Task 3: Self-Contained Web Dashboard (`visualization/web/`)
- 100% offline self-contained (zero npm, zero node_modules, zero external cloud CDNs).
- `visualization/web/templates/index.html`:
  - Responsive 3-column asymmetric layout (`28% : 44% : 28%`):
    - Col 1: AI Debate Arena (Bull vs Bear split-view) + Live Reasoning Feed + TraderProposal card.
    - Col 2: High-performance Candlestick Chart (HTML5 Canvas engine `chart_engine.js`) with crosshair, EMA/RSI overlays, volume, and execution markers.
    - Col 3: L2 Order Book Depth with visual imbalance meter + 6-Layer Guardrail Status Shield + "Frontier Mode" Trade Approval Modal with MetaMask "Confirm On-Chain Swap" CTA.
- `visualization/web/static/css/dashboard.css`:
  - Modern institutional dark-theme, semantic visual hierarchy, accessible color contrast (WCAG AA), crisp typography.
- `visualization/web/static/js/chart_engine.js`:
  - Embedded canvas chart engine supporting real-time candle updates, indicator computation, and pan/zoom.
- `visualization/web/static/js/app.js`:
  - SSE and WebSocket client, state management, and DOM updates.

### Task 4: Jev Design Quality Gate (`visualization/quality/`)
- `visualization/quality/jev_gate.py`:
  - `DesignSummaryExtractor`: Extracts DOM hierarchy, layout geometry, typography contrast, and visual balance.
  - `UIQualityGateValidator`: Invokes local Jev MCP tool `jev_review_design` (or local heuristic engine in tests/offline), verifying:
    - Composite score >= 3.0 / 5.0
    - All sub-scores (brand_fit, visual_quality, clarity, cta_strength) >= 3.0
    - `ready_to_ship == True`
  - FastAPI quality endpoint `/api/design/review` and CLI validation entrypoint.

### Task 5: Comprehensive Unit & Integration Tests
- `tests/unit/test_visualization.py`: Comprehensive test suite for SSE router, WebSocket router, ring buffer, reconnection, and HTML/static serving (aim for >=25 unit tests).
- `tests/unit/test_jev_gate.py`: Comprehensive unit tests for `DesignSummaryExtractor` and `UIQualityGateValidator` (pass/fail thresholds, payload parsing).

## Verification Commands (Must all pass 100%)
1. `python -m pytest tests/unit/test_visualization.py -v`
2. `python -m pytest tests/unit/test_jev_gate.py -v`
3. `python -m pytest tests/e2e/test_tier1_f15_f18_visualization_jev.py -v` (Target: 20/20 passed)
4. `python tests/e2e/run_all.py` (Target: 200/200 passed across Tiers 1-4)
5. `python -m pytest tests/adversarial/ -q` (Target: 173/173 passed)
6. `python -m pytest core/tests/ -q` (Target: 1,420 passed)

Document all commands, stdout/stderr, and exit codes in `handoff.md` and send a completion message back.
