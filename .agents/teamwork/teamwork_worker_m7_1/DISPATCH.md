## 2026-11-09T02:21:22Z
# Worker Dispatch: Milestone 7 Micro-Capital Compounding & MetaMask Execution to $2,000 USD

## Identity
- Archetype: teamwork_worker
- Role: Implementation & Execution Engineer
- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_worker_m7_1

## Mandatory Inputs & Context
- Authoritative User Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md (MANDATORY: Read first)
- Milestone Scope Document: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\orchestrator\SCOPE.md
- Explorer 1 Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_compounding_1\handoff.md
- Explorer 3 Replacement Handoff Report: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_compounding_3_r2\handoff.md
- Domain Skill: c:\Users\AmirM\Documents\Agentic trading\.agent\skills\algorithmic-trading\SKILL.md

## Write Ownership Boundaries
You exclusively own and may edit:
1. `run_live_metamask_terminal.py`
2. `execution/guardrails/pipeline.py`
Do NOT modify unrelated core modules or test harness expectations.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Tasks & Objectives
1. **Dynamic Micro-Capital Sizing in `run_live_metamask_terminal.py`**:
   - Replace the hardcoded `wallet_eth > 0.015` check and `$40.0` fallback in `live_market_and_ai_trading_loop`:
     - Calculate reserved native gas on Layer 2: `reserved_gas_eth = min(0.0001, wallet_eth * 0.08)` (~$0.31 USD).
     - Calculate deployable capital: `deployable_eth = max(0.0, wallet_eth - reserved_gas_eth)`.
     - When total account equity < $25 USD, allocate 75%–85% of deployable capital into a single active rotating position (e.g., `alloc_fraction = 0.85 if t_adx.adx_14 >= 22.0 else 0.75`), yielding ~$2.40–$2.90 USD trade size for 0.0012 ETH (~$3.74 USD).
     - When total account equity >= $25 USD, smoothly transition to standard multi-asset ATR-14 volatility sizing.
2. **Harmonize Pre-Broadcast Guardrail Pipeline in `execution/guardrails/pipeline.py`**:
   - In `PreBroadcastGuardrailPipeline`, allow dynamic micro-capital concentration: when `current_portfolio_value_usd < 25.0`, set the concentration limit to `98.0%` (as proven in `evm_ten_trade_runner.py`), preventing Layer 2 from rejecting single-asset micro-capital trades while maintaining full Honeypot (Layer 1), Slippage (Layer 3), Gas Ceiling (Layer 4), and Simulation (Layer 5) protection.
3. **Continuous Autonomous Compounding Execution**:
   - Ensure the compounding loop reinvests 100% of realized profits back into `wallet_usd` and `wallet_balance_eth`.
   - The loop must run continuously without premature halting on individual trade take-profit events until `cumulative_profit_usd >= 2000.0`.
   - Incorporate the user's explicit directive for full autonomous execution ("do everything autonomus , ineed 2000 $ , you have all my confirmation to buy and sell just do it now ,") via automatic transaction staging and confirmation through `DualEngineWalletRouter` / `EIP1193BridgeServer` without interactive manual browser prompt delays.
4. **Verification & Regression Testing**:
   - Run `python tests/verify_live_terminal_metamask.py` — ensure 8/8 tests pass cleanly.
   - Run `python -m simulation.paper_trader.evm_ten_trade_runner` — ensure micro-capital simulation executes cleanly.
   - Run `python tests/e2e/run_all.py --tier 1` — ensure all 130 tests pass with zero regressions.
   - Document all verification commands and exact outputs in your `handoff.md`.

## Output
Deliver a comprehensive `handoff.md` in your working directory following the Handoff Protocol (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
When complete, notify the orchestrator via `send_message`.
