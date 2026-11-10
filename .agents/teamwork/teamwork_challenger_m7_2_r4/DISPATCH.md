# Challenger 2 Replacement Dispatch (r4): Milestone 7 Gas Drag & Auto-Compounding Adversarial Verification

## Identity
- Archetype: teamwork_challenger
- Role: Code-Executing Adversarial Verifier
- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_2_r4

## Context & Inputs
- Authoritative User Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read first)
- Milestone Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Worker Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md
- Target Files: `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`

## Objective
Empirically challenge the micro-capital compounding implementation by running test commands directly:
1. Run baseline verification commands directly using `run_command`:
   - `python tests/verify_live_terminal_metamask.py`
   - `python -m pytest tests/unit/test_execution.py -v`
   - `python -m pytest tests/adversarial/test_m6_metamask_lifecycle_challenge.py -v`
   - `python -m simulation.paper_trader.evm_ten_trade_runner`
2. Run empirical gas drag and guardrail concentration tests directly using `run_command`:
   - Calculate L2 gas ratio (<1.5% ceiling) and gas cost (<$0.10 cap) for micro-trades ($2.40–$3.00) under typical L2 base fees (0.005–0.05 gwei on Arbitrum/Base).
   - Verify that reserved gas buffer (`min(0.0001, wallet_eth * 0.08)`) prevents native gas depletion across consecutive swaps.
   - Verify Guardrail Layer 2 dynamic concentration (98% for < $25 equity, 20% for >= $25 equity).
   - Verify autonomous compounding reinvestment loop without manual confirmation stalls toward $2,000 USD.
3. Record all executed commands, outputs, and render a definitive verdict (APPROVE or REQUEST_CHANGES) in:
   c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_2_r4\handoff.md
4. Notify the orchestrator via `send_message`. Keep execution concise and focused.


## 2026-11-09T04:47:54Z
You are teamwork_challenger (Challenger 2 r4).
Your working directory is: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_2_r4

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md

Also read your dispatch task details at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_2_r4\DISPATCH.md
and the Worker handoff at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md

Your mission is empirical adversarial verification of gas drag, L2 fee economics, guardrail concentration, and continuous auto-compounding to $2,000 USD in `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`.

EXECUTION INSTRUCTIONS:
Execute commands directly via `run_command` without creating massive test files:
1. Run baseline verification commands directly:
   - `python tests/verify_live_terminal_metamask.py`
   - `python -m pytest tests/unit/test_execution.py -v`
   - `python -m pytest tests/adversarial/test_m6_metamask_lifecycle_challenge.py -v`
   - `python -m simulation.paper_trader.evm_ten_trade_runner`
2. Run empirical gas drag, buffer depletion, and concentration checks via python one-liners:
   - Gas economics: test 145,000 gas at 0.005–0.05 gwei for $2.58–$2.93 trade size against 1.5% ceiling and $0.10 cap.
   - Depletion resistance: simulate 30 consecutive trades deducting gas from 0.0012 ETH to verify `min(0.0001, wallet_eth * 0.08)` always reserves native buffer.
   - Guardrail Layer 2: verify 98% concentration approved for <$25 equity and 20% limit enforced for >=$25 equity.
   - Compounding: verify auto-staging and auto-confirmation without manual popup stalls and target lock at $2,000 USD.
3. Write a concise, structured `handoff.md` in:
   c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_2_r4\handoff.md
   Include: Observation (test commands & outputs), Logic Chain, Caveats, Conclusion (Verdict: APPROVE / REQUEST_CHANGES), Verification Method.
4. When complete, send a message to the orchestrator reporting your verdict and path to handoff.md.
