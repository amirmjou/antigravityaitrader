# Dispatch Task for Worker 1: Security Hardening Implementation

- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_1\
- Project Root: c:\Users\AmirM\Documents\Agentic trading
- Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
- Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Master Project Document: c:\Users\AmirM\Documents\Agentic trading\PROJECT.md
- Survey Reports to read:
  - c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_survey_1\handoff.md
  - c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_survey_2\handoff.md
  - c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_sec_survey_3\handoff.md

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Requirements (Features F27–F33)

1. **Dual-Mode Security & Auth Gateway (F27)**:
   - Create `visualization/server/security.py` with:
     - Security mode detection: `TRADINGAGENTS_SECURITY_MODE` (`"production"` vs `"development"`, default `"development"` in test environments).
     - API key validation: `TRADING_API_KEY` validated via constant-time comparison (`hmac.compare_digest`).
     - Dependency `verify_api_token(credentials, request)`:
       - In `development` mode (when `TRADINGAGENTS_SECURITY_MODE != "production"` and `TRADING_API_KEY` is not set), allow requests through with fallback.
       - In `production` mode (or when `TRADING_API_KEY` is set): check `Authorization: Bearer <TOKEN>` or `X-API-Key: <TOKEN>`.
       - For WebSocket (`/ws/telemetry`, `/ws`) and SSE (`/events/reasoning`), accept token from query parameter `?token=<TOKEN>` if Authorization header is absent.
       - Reject unauthenticated/unauthorized requests with HTTP 401 Unauthorized (`{"detail": "Unauthorized"}`).
     - Public endpoints: `/health` and `/api/health` must remain unauthenticated for healthchecks.
   - Secure endpoints in `visualization/server/app.py`: `/rpc`, `/send-transaction`, `/confirm-transaction`, `/api/performance/100-trades`, `/api/performance/200-trades`.
   - Secure SSE in `visualization/server/sse_router.py`: `/events/reasoning`, `/api/deliberation/stream`.
   - Secure WebSockets in `visualization/server/ws_router.py` and `execution/wallet/eip1193_bridge.py`.

2. **Strict CORS & HTTP Security Headers (F28)**:
   - In `visualization/server/app.py` and `execution/wallet/eip1193_bridge.py`:
     - Allow configurable `ALLOWED_ORIGINS` (comma-separated, default `http://localhost:3000,http://127.0.0.1:3000,http://localhost:8899,http://127.0.0.1:8899`).
     - In development mode without explicit origins, keep development origins, but remove invalid combination of `allow_origins=["*"]` with `allow_credentials=True`.
     - In `sse_router.py`: remove hardcoded `"Access-Control-Allow-Origin": "*"` or match against request origin.
   - Add security headers middleware injecting:
     - `X-Content-Type-Options: nosniff`
     - `X-Frame-Options: DENY`
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
     - `Content-Security-Policy: default-src 'self'; connect-src 'self' wss: https:; script-src 'self'; style-src 'self' 'unsafe-inline'`
     - `Referrer-Policy: strict-origin-when-cross-origin`

3. **Rate Limiting & DoS Defense (F29)**:
   - Implement an in-memory token bucket / sliding window rate limiter in `visualization/server/security.py`:
     - Health checks: high limit (e.g. 120/min).
     - Simulation endpoints (`/api/performance/*`): strict limit (e.g. 5/min) and caching to prevent CPU exhaustion.
     - Transactions & RPC: 30/min.
     - WebSocket/SSE connection limits per IP.

4. **Keystore & Secret Scrubbing Hardening (F30)**:
   - In `execution/wallet/hot_signer.py`:
     - In `save_keystore_file`: Ensure file is written with strict POSIX `0600` permissions (`os.open` with `O_CREAT | O_WRONLY | O_TRUNC` and `0o600` or `os.chmod(..., 0o600)`).
     - Hardening `private_key_hex`: Prevent accidental logging in string representations (`__repr__` and `__str__` must mask the key, e.g. `0x1234...abcd`).
   - In `core/dataflows/net.py` and exception handlers:
     - Add `scrub_secrets(text: str) -> str` that scrubs API keys and URLs with embedded credentials (e.g. `https://arb-mainnet.g.alchemy.com/v2/...`).
   - In `crypto_pipeline/remote_agent/bridge.py`:
     - Whitelist environment variables passed to `subprocess.run(..., env=safe_env)` instead of leaking all parent environment variables.

5. **Production Container & Deployment Hardening (F31)**:
   - Create `Dockerfile` at project root:
     - Multi-stage build (`python:3.11-slim-bookworm`).
     - Dedicated non-root user and group (`appuser:appgroup` UID/GID 10001).
     - App code owned by root (read-only for appuser).
     - Specific writable directories (`/app/keystores`, `/app/data`) with mode 700 owned by `appuser`.
     - Healthcheck instruction.
     - `USER 10001:10001`.
   - Create `docker-compose.prod.yml` at project root:
     - `read_only: true`.
     - `security_opt: [no-new-privileges:true]`.
     - `cap_drop: [ALL]`.
     - `user: "10001:10001"`.
     - Non-root, isolated internal bridge network, volume mounts for keystore data and tmpfs for `/tmp`.
     - Caddy reverse proxy service configuration (`deploy/Caddyfile`).
   - Create `.gitignore` to prevent committing `.env`, `keystores/`, `secrets/`, `*.key`.

6. **Telemetry Circular Import Resolution (F32)**:
   - In `visualization/server/app.py`:
     - Remove eager top-level `from visualization.telemetry.hub import TelemetryHub`.
     - Lazy-import `TelemetryHub` inside `create_visualization_app` when `hub is None`.
     - Verify that `python -m pytest tests/adversarial/test_m3_m4_m5_adversarial_stress.py` passes cleanly!

7. **Security Test Suite & Zero-Regression Verification (F33)**:
   - Create `tests/adversarial/test_security_hardening.py` covering:
     - Unauthenticated requests blocked (401) in production security mode across all protected endpoints (`/rpc`, `/send-transaction`, `/confirm-transaction`, `/api/performance/100-trades`, `/events/reasoning`, `/ws/telemetry`).
     - Authenticated requests succeed with valid `Bearer <TOKEN>` or `?token=<TOKEN>`.
     - Health endpoints (`/health`, `/api/health`) remain accessible without credentials.
     - Security headers present in responses.
     - CORS rejects unauthorized origins.
     - Rate limiter rejects excessive requests (429 Too Many Requests).
     - Keystore file permissions enforce `0600`.
     - Secret scrubbing masks credentials from tracebacks.
     - Subprocess environment whitelisting verification.
     - Dockerfile and docker-compose security attributes verification (non-root UID 10001, cap_drop ALL, no-new-privileges).
   - Execute all verification suites and document exact outputs:
     - `python tests/e2e/run_all.py` (Must pass 200/200, 100%)
     - `python -m pytest tests/unit/ -v` (Must pass 102/102, 100%)
     - `python -m pytest tests/adversarial/test_security_hardening.py -v` (All new security tests must pass)
     - `python -m pytest tests/adversarial/test_m3_m4_m5_adversarial_stress.py -v` (Must pass now that circular import is fixed)

Maintain `progress.md` in your working directory with 'Last visited: [timestamp]'.
Deliver a comprehensive handoff report (`handoff.md`) with build/test results, touched files, and verification commands.


## 2026-11-08T08:03:17Z
[Message] timestamp=2026-11-08T08:03:17Z sender=bcee5896-d8e8-47f7-8d44-cfee1f5051b5 priority=MESSAGE_PRIORITY_HIGH content=You are Worker 1 (Security Hardening Engineer).
Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_1\
Project Root: c:\Users\AmirM\Documents\Agentic trading
Authoritative Request File: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
Dispatch Instructions: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_sec_m6_1\DISPATCH.md
Specialized Domain Skill: c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-cloud-security-architect\SKILL.md
