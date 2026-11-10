# Dispatch Task for Worker 2: Iteration 2 Security Hardening Remediation

- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_2\
- Project Root: c:\Users\AmirM\Documents\Agentic trading
- Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
- Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Explorer 1 Handoff: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_1\handoff.md
- Explorer 2 Handoff: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_it2_2\handoff.md
- Challenger 1 Failure Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_sec_1\handoff.md

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Remediation Objectives

1. **Fix Non-ASCII Token `TypeError` in `visualization/server/security.py`**:
   - In `verify_token_string(token)` (line 62–72):
     Safely encode both `token` and `expected` to UTF-8 bytes before comparing with `hmac.compare_digest`:
     ```python
     def verify_token_string(token: Optional[str]) -> bool:
         if not is_auth_enforced():
             return True
         expected = get_configured_api_key()
         if not expected or not token:
             return False
         try:
             token_bytes = token.encode("utf-8") if isinstance(token, str) else bytes(token)
             expected_bytes = expected.encode("utf-8") if isinstance(expected, str) else bytes(expected)
             return hmac.compare_digest(token_bytes, expected_bytes)
         except (TypeError, UnicodeEncodeError, Exception):
             return False
     ```
   - In `check_websocket_auth(websocket)`:
     Ensure token extraction and verification are wrapped in `try...except Exception: return False` so non-ASCII or malformed query strings never throw unhandled exceptions.

2. **Clean WebSocket Close Code 1008 in `visualization/server/ws_router.py`**:
   - Ensure `if not check_websocket_auth(websocket): await websocket.close(code=1008, reason="Unauthorized"); return` handles all invalid, malformed, or non-ASCII tokens cleanly.

3. **Protect `/pending` (and `/request-accounts`) in `execution/wallet/eip1193_bridge.py`**:
   - In lines 268–270:
     Add authentication dependency to `list_pending`:
     ```python
     @app.get("/pending")
     async def list_pending(_token: str = Depends(verify_api_token)):
         return {"pending": list(server.pending_transactions.values())}
     ```
   - In lines 221–224:
     Add authentication dependency to `request_accounts`:
     ```python
     @app.get("/request-accounts")
     @app.post("/request-accounts")
     async def request_accounts(_token: str = Depends(verify_api_token)):
         return {"accounts": server.connected_accounts}
     ```

4. **Add Regression Tests in `tests/adversarial/test_security_hardening.py`**:
   - Add tests verifying non-ASCII tokens (`🔑`, Chinese chars, null bytes) safely return `False` without `TypeError`.
   - Add test verifying `GET /pending` and `GET /request-accounts` return HTTP 401 when unauthenticated in production mode.

5. **Test Verification Requirements**:
   Run and verify that all test suites pass with 100% success rate:
   - `python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v` (Must pass all 68/68 tests, 0 failures)
   - `python -m pytest tests/adversarial/test_security_hardening.py -v` (Must pass all tests)
   - `python -m pytest tests/adversarial/test_sec_empirical_stress.py -v` (Must pass all 23 tests)
   - `python -m pytest tests/unit/ -v` (Must pass all 102 tests)
   - `python tests/e2e/run_all.py` (Must pass all 200/200 tests)

Maintain progress.md in your working directory with 'Last visited: [timestamp]'.
Deliver a comprehensive handoff report (`handoff.md`) with build/test results, touched files, and verification commands.

## 2026-11-08T08:43:37Z
You are Worker 2 (Security Remediation Engineer).
Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_2\
Project Root: c:\Users\AmirM\Documents\Agentic trading
Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
Dispatch Instructions: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_2\DISPATCH.md
Specialized Domain Skill: c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-cloud-security-architect\SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your exclusive write ownership:
- visualization/server/security.py
- visualization/server/ws_router.py
- execution/wallet/eip1193_bridge.py
- tests/adversarial/test_security_hardening.py

Implement the 4 remediation tasks specified in DISPATCH.md:
1. Fix non-ASCII token comparison in `visualization/server/security.py` using UTF-8 bytes and `try...except`.
2. Ensure WebSocket cleanly closes with code 1008 on unauthorized/malformed tokens in `ws_router.py`.
3. Protect `/pending` and `/request-accounts` in `execution/wallet/eip1193_bridge.py` with `_token: str = Depends(verify_api_token)`.
4. Add regression tests to `tests/adversarial/test_security_hardening.py`.

Run all test suites via run_command to verify:
1. python -m pytest tests/adversarial/test_m6_adversarial_challenge.py -v (all 68/68 must pass, 0 failures)
2. python -m pytest tests/adversarial/test_security_hardening.py -v (all pass)
3. python -m pytest tests/adversarial/test_sec_empirical_stress.py -v (all 23 pass)
4. python -m pytest tests/unit/ -v (all 102 pass)
5. python tests/e2e/run_all.py (all 200/200 pass)

Maintain progress.md in your working directory with 'Last visited: [timestamp]'.
Deliver a comprehensive handoff report (`handoff.md`) with verified test outputs and notify parent orchestrator via send_message when complete.
