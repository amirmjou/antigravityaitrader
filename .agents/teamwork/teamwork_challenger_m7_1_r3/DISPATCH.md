# Challenger 1 Replacement Dispatch: Milestone 7 Boundary Adversarial Verification

## Identity
- Archetype: teamwork_challenger
- Role: Code-Executing Adversarial Verifier (Challenger 1 Replacement)
- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r3

## Context & Inputs
- Authoritative User Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read first)
- Milestone Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Worker Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1\handoff.md
- Target Files: `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`

## Objective
Empirically challenge the micro-capital compounding implementation with stress tests and edge cases:
1. Micro-Capital Boundary & Underflow Testing:
   - What happens if `wallet_balance_eth = 0.00005` (below reserved gas)? Does `deployable_eth` go negative or produce valid bounds?
   - What happens if `wallet_balance_eth = 0.0` or negative?
   - What happens at the transition boundary `current_portfolio_value_usd = 24.99` vs `25.01`? Does concentration cap transition cleanly from 98% to 20%?
2. Compounding Target Boundary:
   - Does the loop cleanly detect reaching or exceeding `$2,000 USD` cumulative profit and lock/terminate appropriately without infinite runaway execution?
3. Execute your adversarial tests and scripts directly, plus run baseline tests:
   - `python tests/verify_live_terminal_metamask.py`
   - `python tests/e2e/run_all.py --tier 1`
   - `python -m simulation.paper_trader.evm_ten_trade_runner`
4. Render a clear verdict: **APPROVE** or **REQUEST_CHANGES**.

Deliver a comprehensive `handoff.md` in your working directory (`c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_challenger_m7_1_r3\handoff.md`) and notify the orchestrator via `send_message`.
