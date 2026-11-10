# Dispatch Task for Explorer 2 (Iteration 2 Fix Strategy - Transport & Auth Hardening)

- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_2\
- Project Root: c:\Users\AmirM\Documents\Agentic trading
- Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
- Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Challenger 1 Handoff: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_sec_1\handoff.md
- Gate Status: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\GATE_STATUS.md

## Iteration 1 Failure Details
Challenger 1 executed `tests/adversarial/test_m6_adversarial_challenge.py` and uncovered 2 vulnerabilities:
1. `visualization/server/security.py:71`: `hmac.compare_digest(token, expected)` raises `TypeError: comparing strings with non-ASCII characters is not supported` on Unicode/emoji tokens in query params and WebSocket handshakes.
2. `execution/wallet/eip1193_bridge.py:268`: `GET /pending` lacks authentication, allowing unauthenticated network callers to view pending transactions in production mode.

## Mission
Analyze the transport and authentication layer:
- Investigate UTF-8 byte encoding versus string comparison across all token verification pathways (`verify_api_token`, `check_websocket_auth`, header parser).
- Inspect WebSocket handshake error handling to ensure invalid tokens close with clean code 1008 under all exception conditions.
- Propose specific, robust code changes for Worker 2.

Deliver a structured `handoff.md` in your working directory.


## 2026-11-08T08:32:43Z
You are Explorer 2 (Iteration 2 Fix Strategy - Transport & Auth Hardening).
Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_2\
Project Root: c:\Users\AmirM\Documents\Agentic trading
Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
Challenger 1 Handoff: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_sec_1\handoff.md
Gate Status: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\GATE_STATUS.md
Dispatch Instructions: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_2\DISPATCH.md

Investigate transport and authentication hardening for:
1. Safe UTF-8 byte encoding and exception handling in `verify_token_string` and `check_websocket_auth`.
2. Safe WebSocket closure with code 1008 on all malformed/non-ASCII tokens.
3. Formulate specific code changes for Worker 2.

Maintain progress.md in your working directory with 'Last visited: [timestamp]'.
Deliver handoff.md and notify parent via send_message when complete.
