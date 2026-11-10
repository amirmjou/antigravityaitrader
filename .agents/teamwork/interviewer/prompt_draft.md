Execute automated crypto trading starting with 0.0012 ETH (~$3.74 USD) from the connected MetaMask wallet, running a compounding trading loop until reaching the target portfolio valuation of $2,000 USD.

Working directory: c:\Users\AmirM\Documents\Agentic trading
Integrity mode: development

## Requirements

### R1. Micro-Capital Trading and Compounding Execution
Configure and execute the trading engine to manage and grow the micro-capital balance of 0.0012 ETH (~$3.74 USD) toward the $2,000 USD target, using an automated compounding strategy with fractional allocation per trade.

### R2. Low-Fee Network Routing
Route trading operations through low-fee Layer 2 networks (such as Base or Arbitrum) to ensure network transaction costs remain micro-scale (~$0.02–$0.05 per transaction) and do not deplete the 0.0012 ETH starting capital.

### R3. MetaMask Bridge Integration and Safety Controls
Execute trades via the live terminal and MetaMask EIP-1193 bridge active on `http://127.0.0.1:8899/?token=ag_live_metamask_2026_token`, enforcing ATR-based stop-loss protections and trade safety checks.

### R4. Automated Verification and Telemetry
Verify strategy logic, order routing, and safety mechanisms programmatically using dry-run simulation and automated test suites before live order dispatch, while maintaining real-time telemetry and balance tracking toward the $2,000 USD target.

## Verification Resources
- Verification suites: `tests/verify_live_terminal_metamask.py`, `tests/e2e/run_all.py`
- Simulation environment: `simulation/paper_trader/`
- Live MetaMask bridge endpoint: `http://127.0.0.1:8899/?token=ag_live_metamask_2026_token`

## Acceptance Criteria

### Strategy and Compounding Execution
- [ ] The trading engine successfully initializes with the 0.0012 ETH wallet balance and calculates order sizes based on fractional capital allocation.
- [ ] The compounding loop executes trades progressively toward the $2,000 USD target without prematurely halting when in profit.
- [ ] Transactions are routed on low-fee Layer 2 networks (Base or Arbitrum) with gas costs per swap verified below $0.10.

### Bridge and Order Execution
- [ ] Trade proposals and transactions are dispatched through the active MetaMask bridge at `http://127.0.0.1:8899/?token=ag_live_metamask_2026_token`.
- [ ] Stop-loss and risk guardrails (including ATR protection) reject trades that violate risk limits.

### Automated Verification
- [ ] Automated verification scripts in `tests/verify_live_terminal_metamask.py` and simulation tests run cleanly without regressions.
- [ ] Telemetry logs accurately record starting balance (0.0012 ETH), executed orders, transaction fees, and live balance progress toward the $2,000 USD target.
