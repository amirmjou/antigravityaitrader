# BRIEFING — 2026-11-09T03:22:30Z

## Mission
Remediate live terminal server and MetaMask bridge input validation vulnerabilities (Chain ID sanitization, Ethereum address validation, non-dict/non-scalar crash prevention) with zero test regressions.

## 🔒 My Identity
- Archetype: teamwork_worker
- Roles: implementer, qa, specialist (Terminal and Bridge Remediation Implementer)
- Working directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m6_2\
- Original parent: 56b3c564-3f59-4841-ab4a-c6a6e410c34a
- Milestone: Milestone 6 (Terminal and Bridge Remediation)

## 🔒 Key Constraints
- Exclusive file ownership:
  - `visualization/server/app.py`
  - `execution/wallet/eip1193_bridge.py`
  - `tests/adversarial/test_m6_metamask_lifecycle_challenge.py`
- DO NOT CHEAT: genuine implementation, no dummy facade or hardcoded outputs.
- Enforce strict EIP-155 (chain_id > 0) and Ethereum hex address format (`^0x[0-9a-fA-F]{40}$`).
- Reject non-dict and malformed payloads with HTTP 400 without crashing with HTTP 500.
- Update dummy addresses in `tests/adversarial/test_m6_metamask_lifecycle_challenge.py` from dummy non-hex strings to valid 40-character hex strings (`0x1111111111111111111111111111111111111111`, `0x2222222222222222222222222222222222222222`).
- 100% test passes across all suites:
  - `python tests/adversarial/test_m6_live_endpoint_stress.py` (44/44)
  - `python -m pytest tests/adversarial/test_m6_metamask_lifecycle_challenge.py -v` (23/23)
  - `python tests/verify_live_terminal_metamask.py` (8/8)
  - `python -m pytest tests/unit -q` (102/102)
  - `python tests/e2e/run_all.py` (200/200)
  - `python -m pytest tests/adversarial/test_security_hardening.py tests/adversarial/test_m6_adversarial_challenge.py -q` (100/100)

## Current Parent
- Conversation ID: 56b3c564-3f59-4841-ab4a-c6a6e410c34a
- Updated: not yet

## Task Summary
- **What to build**: Implement `sanitize_chain_id`, `ETH_ADDRESS_REGEX`, robust payload parsing and validation in `direct_wallet_sync_account` and `json_rpc_proxy` in `visualization/server/app.py`, address validation defense-in-depth in `execution/wallet/eip1193_bridge.py`, and test address adjustments in `tests/adversarial/test_m6_metamask_lifecycle_challenge.py`.
- **Success criteria**: All stress, unit, adversarial, and e2e test suites pass with 0 failures and 0 regressions.
- **Interface contracts**: REST `/wallet_syncAccount` and JSON-RPC 2.0 `/rpc`.
- **Code layout**: `visualization/server/app.py`, `execution/wallet/eip1193_bridge.py`, `tests/`.

## Key Decisions Made
- Use `sanitize_chain_id` helper in `visualization/server/app.py` returning `int`, rejecting `None`, `bool`, floats, negative numbers, 0, or malformed non-scalar types.
- Require `ETH_ADDRESS_REGEX.match(account)` for address sync.
- Preserve initial state `["0xUserWallet"]` in `eip1193_bridge.py` for backward compatibility with baseline unit tests.

## Artifact Index
- `.agents/teamwork/teamwork_worker_m6_2/DISPATCH.md` — Assigned task instructions
- `.agents/teamwork/teamwork_worker_m6_2/BRIEFING.md` — Agent persistent state and memory
- `.agents/teamwork/teamwork_worker_m6_2/progress.md` — Heartbeat and execution step tracking
- `.agents/teamwork/teamwork_worker_m6_2/skills/` — Local dumps of associated skills
- `.agents/teamwork/teamwork_worker_m6_2/handoff.md` — Self-contained final handoff report

## Change Tracker
- **Files modified**: None yet
- **Build status**: Initial state — 5 tests failing in `test_m6_live_endpoint_stress.py`
- **Pending issues**: None

## Quality Status
- **Build/test result**: 39/44 passing in stress suite prior to remediation
- **Lint status**: Pending checks
- **Tests added/modified**: `test_m6_metamask_lifecycle_challenge.py` test addresses to be updated

## Loaded Skills
- **Source**: `c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-api-tester\SKILL.md`
  - **Local copy**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m6_2\skills\agency-api-tester.md`
  - **Core methodology**: Comprehensive API validation, security assertions (OWASP Top 10), payload fuzzing, input sanitization, and SLA verification.
- **Source**: `c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-realtime-collaboration-engineer\SKILL.md`
  - **Local copy**: `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m6_2\skills\agency-realtime-collaboration-engineer.md`
  - **Core methodology**: Realtime sync protocols, idempotent ops, connection lifecycle management, and hostile network survival.
