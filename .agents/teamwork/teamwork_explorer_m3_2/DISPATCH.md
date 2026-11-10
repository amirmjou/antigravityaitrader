# Dispatch Assignment: Milestone 3 Explorer 2 (Streaming Telemetry & Real-Time Events)

## Mission
Investigate and specify the dual-channel streaming architecture for live agent reasoning (Server-Sent Events) and real-time market/trade telemetry (WebSockets) (Features F16 & F17).

## Mandatory Context
Read `ORIGINAL_REQUEST.md` verbatim:
`c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md`

Read `PROJECT.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\PROJECT.md`

Read `TEST_INFRA.md` at root:
`c:\Users\AmirM\Documents\Agentic trading\TEST_INFRA.md`

## Investigation Scope & Questions
1. Design the FastAPI streaming endpoints:
   - **SSE Endpoint (`/events/reasoning`)**:
     - Format: `text/event-stream` with structured JSON data frames (`event: agent_thought`, `event: debate_argument`, `event: tool_call`, `event: proposal_generated`).
     - Event payload contracts: agent name, role, timestamp, token/chunk content, debate round, consensus status.
     - Integration with LangGraph agent streaming and callback handlers.
   - **WebSocket Endpoint (`/ws/telemetry`)**:
     - Full-duplex connection for live K-line/OHLCV updates, order book bid/ask depth snapshots, simulated/live execution events, and active guardrail state.
     - Reconnection handling, heartbeat ping/pong, and multi-client broadcast manager (`ConnectionManager`).
2. Examine existing E2E tests for F15–F18 in `tests/e2e/test_tier1_f15_f18_visualization.py` (if any, or corresponding tier 1 tests) to ensure 100% compatibility with existing test expectations and assertion contracts.
3. Define exact data schemas (Pydantic models) and router blueprints for the Worker.

Deliver `analysis.md` and `handoff.md` in your working directory and notify the parent orchestrator via send_message.

## 2026-11-06T19:39:35Z
You are teamwork_explorer_m3_2, Explorer 2 for Milestone 3 (Streaming Telemetry & Real-Time Events).
Your working directory is c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_2\

Read your dispatch instructions in your working directory:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m3_2\DISPATCH.md

Read ORIGINAL_REQUEST.md verbatim:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md

Read PROJECT.md at root:
c:\Users\AmirM\Documents\Agentic trading\PROJECT.md

Investigate FastAPI SSE (/events/reasoning) and WebSocket (/ws/telemetry) streaming architecture and data schemas.
Deliver analysis.md and handoff.md in your working directory and notify the parent orchestrator via send_message.
