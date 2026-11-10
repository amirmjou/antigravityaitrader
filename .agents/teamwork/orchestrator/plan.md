# Milestone 7 Execution Plan: Micro-Capital Compounding & MetaMask Execution to $2,000 USD

## Objective
Configure and execute automated crypto trading starting from 0.0012 ETH (~$3.74 USD) synced from the connected MetaMask wallet on port 8899 (`http://127.0.0.1:8899/?token=ag_live_metamask_2026_token`), running an autonomous compounding trading loop across low-fee L2 networks (Base/Arbitrum) with gas <$0.10, ATR stop-loss protections, and real-time telemetry until reaching the target portfolio valuation of $2,000 USD.

## Requirements Alignment
- **R1: Micro-Capital Trading & Compounding Execution**: Dynamic micro-gas reserve (`min(0.0001 ETH, wallet_eth * 0.08)` / ~$0.31), fractional single-position allocation (75%–85% for equity <$25, ATR-14 for >=$25), continuous compounding loop without premature halting on take-profit.
- **R2: Low-Fee Network Routing**: Swap routing on Base (8453) and Arbitrum One (42161) with gas costs per swap verified below $0.10 (~$0.02–$0.05).
- **R3: MetaMask Bridge Integration & Safety Controls**: Active live bridge on port 8899, ATR stop-loss protection, 5-layer pre-broadcast safety pipeline (Honeypot, Concentration 98%, Slippage, Gas, Simulation), autonomous order execution without manual confirmation prompts per user directive.
- **R4: Automated Verification & Telemetry**: Programmatic verification via `tests/verify_live_terminal_metamask.py`, `simulation/paper_trader/evm_ten_trade_runner.py`, and E2E suites; real-time telemetry of starting balance (0.0012 ETH), executed orders, fees, and balance progress toward $2,000 USD.

## Iteration 1 Workflow
1. **Worker**: Implement micro-capital sizing and autonomous continuous compounding in `run_live_metamask_terminal.py` and `execution/guardrails/pipeline.py`. Execute verification suites (`tests/verify_live_terminal_metamask.py`, `evm_ten_trade_runner.py`, `run_all.py --tier 1`).
2. **Reviewers (2 parallel)**: Independently inspect code correctness, gas protection (<$0.10), ATR stop-loss enforcement, and non-regression across test suites.
3. **Challengers (2 parallel)**: Adversarially stress-test micro-capital corner cases (zero balance, micro balance depletion, gas spikes, network mismatch, race conditions).
4. **Forensic Auditor**: Verify genuine implementation without stubs, hardcoded balance values, or mock shortcuts.
5. **Quality Gate**: Evaluate all verdicts in `GATE_STATUS.md`. Pass only if all approve with zero integrity violations.
