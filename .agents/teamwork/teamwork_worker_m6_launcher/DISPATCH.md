## 2026-11-09T00:25:53Z
You are teamwork_worker_m6_launcher.
Your role: Live Terminal Daemon Launcher and Verifier.
Your working directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m6_launcher\
Original request file: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
Project root: c:\Users\AmirM\Documents\Agentic trading

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY FIRST STEP: Read c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md.

Task Objectives:
1. Check port 8899 on `127.0.0.1`. If an old process is holding it, cleanly terminate it.
2. Start and keep running the live trading bot terminal service (`run_live_metamask_terminal.py`) on `http://127.0.0.1:8899` as a background process / daemon.
   (e.g., using `Start-Process -FilePath "python" -ArgumentList "run_live_metamask_terminal.py" -NoNewWindow` or `run_command` with `IsDaemon=true`).
3. Poll `http://127.0.0.1:8899/health` until it returns HTTP 200 `{"status": "ok", ...}` (with a 15-second timeout).
4. Verify the live acceptance criteria via HTTP requests:
   - `http://127.0.0.1:8899/?token=ag_live_metamask_2026_token` returns HTTP 200 with HTML content.
   - `http://127.0.0.1:8899/` (no token) returns HTTP 401.
   - `http://127.0.0.1:8899/?token=invalid` returns HTTP 401.
5. Verify live WebSocket connection to `ws://127.0.0.1:8899/ws/telemetry?token=ag_live_metamask_2026_token` and SSE connection to `http://127.0.0.1:8899/events/reasoning?token=ag_live_metamask_2026_token`.
6. Confirm the server remains alive and listening on `http://127.0.0.1:8899`.
7. Write your execution report with PID, ports, HTTP responses, and live telemetry confirmation to `handoff.md` and notify orchestrator via send_message.
