# Challenger 1 Replacement Dispatch (r4): Milestone 7 Boundary Adversarial Verification

## Identity
- Archetype: teamwork_challenger
- Role: Code-Executing Adversarial Verifier
- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r4

## Context & Inputs
- Authoritative User Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read first)
- Milestone Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Worker Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md
- Target Files: `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`

## Objective
Empirically verify the micro-capital compounding implementation by running concrete test suites and empirical test scripts:
1. Run baseline verification commands directly:
   - `python tests/verify_live_terminal_metamask.py`
   - `python tests/e2e/run_all.py --tier 1`
   - `python -m simulation.paper_trader.evm_ten_trade_runner`
2. Run boundary stress verification directly:
   - `python -c "from run_live_metamask_terminal import calculate_micro_capital_sizing; print('Zero:', calculate_micro_capital_sizing(0.0, 3120.0, 25.0)); print('Neg:', calculate_micro_capital_sizing(-0.1, 3120.0, 25.0)); print('SubGas:', calculate_micro_capital_sizing(0.00005, 3120.0, 25.0)); print('Sub25:', calculate_micro_capital_sizing(0.0079, 3120.0, 25.0)); print('Over25:', calculate_micro_capital_sizing(0.0081, 3120.0, 25.0, atr_14=45.0, target_price=3120.0))"`
   - Verify that 0.0 or negative balances cleanly return (0.0, 0.0), microscopic balances preserve gas, and $24.99 vs $25.01 transitions smoothly.
3. Verify target profit lock at $2,000 USD (in `run_live_metamask_terminal.py` lines 401–407).
4. Render a clear verdict: **APPROVE** or **REQUEST_CHANGES**.

Write a structured `handoff.md` in `c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r4\handoff.md` with:
- Observation (test commands executed & outputs)
- Logic Chain
- Caveats
- Conclusion (Verdict: APPROVE / REQUEST_CHANGES)
- Verification Method

Notify the orchestrator via `send_message`.

## 2026-11-09T04:29:06Z
You are teamwork_challenger (Challenger 1 r4).
Your working directory is: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r4

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md

Also read your dispatch task details at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r4\DISPATCH.md
and the Worker handoff at:
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md

Your mission is empirical adversarial boundary verification of the micro-capital compounding implementation in `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`.
1. Run baseline verification commands directly using `run_command`:
   - `python tests/verify_live_terminal_metamask.py`
   - `python tests/e2e/run_all.py --tier 1`
   - `python -m simulation.paper_trader.evm_ten_trade_runner`
2. Run empirical boundary stress tests directly using `run_command`:
   - Test 0.0, negative balances, and sub-gas balances:
     python -c "from run_live_metamask_terminal import calculate_micro_capital_sizing; print('Zero:', calculate_micro_capital_sizing(0.0, 3120.0, 25.0)); print('Neg:', calculate_micro_capital_sizing(-0.1, 3120.0, 25.0)); print('SubGas:', calculate_micro_capital_sizing(0.00005, 3120.0, 25.0)); print('Sub25:', calculate_micro_capital_sizing(0.0079, 3120.0, 25.0)); print('Over25:', calculate_micro_capital_sizing(0.0081, 3120.0, 25.0, atr_14=45.0, target_price=3120.0))"
   - Verify smooth transition at $24.99 vs $25.01 equity and target profit lock at $2,000 USD.
3. Record all executed commands, outputs, and render a definitive verdict (APPROVE or REQUEST_CHANGES) in:
   c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r4\handoff.md
4. When complete, send a message to the orchestrator reporting your verdict and path to handoff.md. Keep execution concise and focused.
