# Forensic Auditor Dispatch: Milestone 7 Integrity Verification

## Identity
- Archetype: teamwork_auditor
- Role: Forensic Integrity Auditor
- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_auditor_m7_1

## Context & Inputs
- Authoritative User Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read first)
- Milestone Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Worker Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md
- Modified files: `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`

## Objective
Perform independent forensic integrity auditing on the changes made by Worker 1:
1. Static Analysis:
   - Check `run_live_metamask_terminal.py` for any hardcoded test outputs, fake balances, mock shortcuts, or bypassed calculations.
   - Verify that `calculate_micro_capital_sizing` implements genuine mathematical calculations for gas reserve and deployable capital.
   - Check `execution/guardrails/pipeline.py` for genuine concentration logic without backdoor overrides.
2. Runtime Tracing & Execution Validation:
   - Run verification commands (`tests/verify_live_terminal_metamask.py`, `simulation.paper_trader.evm_ten_trade_runner`, `tests/e2e/run_all.py --tier 1`).
   - Confirm that tests actually execute code paths rather than relying on tautological assertions.
3. Integrity Verdict:
   - Report a clear, unambiguous binary verdict: **CLEAN** or **INTEGRITY VIOLATION**.

Deliver a comprehensive `handoff.md` in your working directory and notify the orchestrator via `send_message`.

## 2026-11-09T02:37:34Z
You are the Forensic Integrity Auditor for Milestone 7.
Working directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_auditor_m7_1

MANDATORY: Read c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Also read:
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_auditor_m7_1\DISPATCH.md
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md

Perform thorough forensic integrity checks on `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`:
1. Static analysis: check for hardcoded test results, fake balances, mock shortcuts, bypasses.
2. Runtime tracing & execution validation: run test commands and verify genuine execution.
3. Integrity Verdict: CLEAN or INTEGRITY VIOLATION.

Deliver a comprehensive handoff.md in your working directory and notify orchestrator via send_message.
