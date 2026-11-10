## 2026-11-09T00:07:21Z
You are teamwork_worker_m6_2_r2.
Your role: Terminal and Bridge Remediation Implementer (Replacement).
Your working directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m6_2_r2\
Original request file: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
Project root: c:\Users\AmirM\Documents\Agentic trading
Associated Skills:
- c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-api-tester\SKILL.md
- c:\Users\AmirM\Documents\Agentic trading\.agent\skills\agency-realtime-collaboration-engineer\SKILL.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY FIRST STEP: Read c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read the reports from Challenger 1, Explorer 2, and Explorer 3:
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m6_1\handoff.md
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m6_it2_2\handoff.md
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_m6_it2_3\handoff.md

Your Exclusive File Ownership:
- visualization/server/app.py
- execution/wallet/eip1193_bridge.py
- tests/adversarial/test_m6_metamask_lifecycle_challenge.py

Remediation Tasks:
1. In `visualization/server/app.py`:
   - Implement `sanitize_chain_id(val: Any) -> int`:
     - Reject None -> ValueError
     - Reject bool -> TypeError (e.g. `isinstance(val, bool)`)
     - Accept int / string (decimal or 0x hex) -> convert -> require `cid > 0` (EIP-155) -> return `cid`
     - Reject all else -> TypeError/ValueError
   - Add `ETH_ADDRESS_REGEX = re.compile(r"^0x[0-9a-fA-F]{40}$")`.
   - In `direct_wallet_sync_account` (`POST /wallet_syncAccount`):
     - Safely parse request body:
       If `not isinstance(body, dict)`:
         If `isinstance(body, list) and len(body) > 0`:
           account = body[0] if isinstance(body[0], str) else None
           chain_id = body[1] if len(body) > 1 else None
         Else raise `HTTPException(status_code=400, detail="Payload must be a JSON object or array")`
       Else:
         extract `account` from `account`, `address`, or `params[0]`.
         extract `chain_id` from `chain_id` or `params[1]`.
     - Validate address:
       If `not account or not isinstance(account, str) or not ETH_ADDRESS_REGEX.match(account)`:
         raise `HTTPException(status_code=400, detail="Invalid Ethereum address format")`
       app.state.bridge_server.set_connected_account(account)
     - Validate chain ID:
       If `chain_id is not None`:
         try:
           cid = sanitize_chain_id(chain_id)
           app.state.bridge_server.chain_id = cid
         except (ValueError, TypeError) as exc:
           raise `HTTPException(status_code=400, detail=f"Invalid chain_id: {exc}")`
   - In `json_rpc_proxy` (`POST /rpc`):
     - In `method == "wallet_syncAccount"`:
       If `params and isinstance(params[0], str) and ETH_ADDRESS_REGEX.match(params[0])`:
         app.state.bridge_server.set_connected_account(params[0])
       If `len(params) > 1 and params[1] is not None`:
         try:
           cid = sanitize_chain_id(params[1])
           app.state.bridge_server.chain_id = cid
         except (ValueError, TypeError) as exc:
           return {"jsonrpc": "2.0", "id": rpc_req.id, "error": {"code": -32602, "message": f"Invalid params: {exc}"}}

2. In `execution/wallet/eip1193_bridge.py`:
   - In `set_connected_account(self, address: str)`:
     Add defense-in-depth: if `address != "0xUserWallet"` and not `ETH_ADDRESS_REGEX.match(address)`: do not insert or reject. (Preserve `["0xUserWallet"]` initialization for existing tests).

3. In `tests/adversarial/test_m6_metamask_lifecycle_challenge.py`:
   - In `test_rpc_wallet_sync_account_variations`:
     Replace dummy strings `"0xHexWallet"` and `"0xDecWallet"` with valid 42-char hex strings:
     e.g., `"0x1111111111111111111111111111111111111111"` and `"0x2222222222222222222222222222222222222222"`.

4. Run Independent Verification:
   - `python tests/adversarial/test_m6_live_endpoint_stress.py` (Must pass 44/44!)
   - `python -m pytest tests/adversarial/test_m6_metamask_lifecycle_challenge.py -v` (Must pass 23/23!)
   - `python tests/verify_live_terminal_metamask.py` (Must pass 8/8!)
   - `python -m pytest tests/unit -q` (Must pass 102/102!)
   - `python tests/e2e/run_all.py` (Must pass 200/200!)
   - `python -m pytest tests/adversarial/test_security_hardening.py tests/adversarial/test_m6_adversarial_challenge.py -q` (Must pass 100/100!)
   Verify 100% tests pass with ZERO regressions.

5. Document all executed changes, test commands, outputs, and verification results in `handoff.md` in your working directory.
6. Communicate back to the orchestrator via send_message when done.
