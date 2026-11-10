# Scope: Micro-Capital Compounding & MetaMask Execution to $2,000 USD

## Architecture
The automated crypto trading system manages micro-capital starting from 0.0012 ETH (~$3.74 USD) synced from the connected MetaMask wallet on port 8899 (`http://127.0.0.1:8899/?token=ag_live_metamask_2026_token`). Trades are executed continuously and autonomously across low-fee Layer 2 networks (Arbitrum One 42161 and Base 8453) via Uniswap v3 SwapRouter02 and Aerodrome. Pre-broadcast risk controls enforce ATR-14 stop-loss protection and a 5-layer safety pipeline, while realized profits are 100% compounded until reaching the target portfolio valuation of $2,000 USD.

```
  [MetaMask Wallet (0.0012 ETH)] ───► POST /wallet_syncAccount (Port 8899)
                 │
                 ▼
  [Live Market & AI Deliberation] ◄─── (BTC, ETH, SOL Technical Indicators)
                 │
                 ▼
  [Dynamic Micro-Capital Sizer]
  - Reserved L2 Gas: min(0.0001 ETH, wallet_eth * 0.08) (~$0.31 USD)
  - Deployable Capital: wallet_eth - reserved_gas
  - Micro-Tier Allocation (<$25): 75%–85% into single active position (~$2.40–$2.90)
  - Growth-Tier Allocation (>= $25): Multi-asset ATR-14 volatility sizing
                 │
                 ▼
  [Pre-Broadcast Safety Pipeline]
  - Layer 1: GoPlus Honeypot & Mintable Contract Verification
  - Layer 2: Capital Allocation & Concentration (98% for micro-tier, 20% for growth)
  - Layer 3: Dynamic Slippage & Price Impact (< 2.0%)
  - Layer 4: L2 Gas & Congestion Ceiling (< $0.10 gas per swap)
  - Layer 5: eth_call Pre-Flight Simulation
                 │
                 ▼ Approved Transaction
  [Autonomous Execution Engine]
  - DualEngineWalletRouter / EIP-1193 Bridge Server
  - Direct execution without manual confirmation prompts (authorized by user)
  - Swap execution on Arbitrum One (42161) or Base (8453)
                 │
                 ▼
  [Continuous Compounding Engine]
  - Round-trip PnL realized (gross PnL - DEX fee - L2 gas)
  - Compounding update: wallet_usd += net_pnl, wallet_eth = wallet_usd / eth_px
  - Loop executes continuously until cumulative_profit_usd >= 2000.0 USD
                 │
                 ▼
  [Telemetry Hub & Verification]
  - Live WebSocket (/ws/telemetry) & SSE (/events/reasoning) broadcasts
  - Starting balance (0.0012 ETH), executed orders, fees, live balance progress
  - Programmatic verification suite tests/verify_live_terminal_metamask.py
```

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F31 | Micro-Capital Balance Ingestion | Ingestion and real-time synchronization of 0.0012 ETH starting balance from MetaMask wallet via `/wallet_syncAccount` and `/rpc` | M7 | Survey (R1, R3) |
| F32 | Dynamic L2 Micro-Capital Sizing | Calculation of micro-capital order sizes reserving L2 gas (`min(0.0001 ETH, wallet_eth * 0.08)`) and fractional allocation (75%–85% for equity <$25, ATR-14 for >=$25) replacing 0.015 ETH / $40 fallback | M7 | Survey (R1, R2) |
| F33 | Low-Fee L2 Network Routing | Routing of swaps through Arbitrum One (42161) and Base (8453) DEX routers with gas costs strictly verified < $0.10 per transaction (~$0.02–$0.05) | M7 | Survey (R2) |
| F34 | Micro-Capital Guardrail Harmonization | Dynamic asset concentration (98% for equity <$25, 20% for >=$25) ensuring single-position micro-trades pass Layer 2 pre-broadcast checks | M7 | Survey (R2, R3) |
| F35 | Autonomous Bridge & Order Execution | Direct autonomous order execution via `DualEngineWalletRouter` and `EIP1193BridgeServer` without interactive manual confirmation prompts per user directive | M7 | Survey (R3, Follow-up) |
| F36 | Continuous Compounding Loop to $2,000 | Continuous trade execution reinvesting 100% of realized profits into subsequent trades without premature halting until reaching $2,000 USD portfolio valuation | M7 | Survey (R1) |
| F37 | Real-Time Telemetry & Target Tracking | Telemetry streaming over WebSocket and SSE recording starting balance, executed orders, L2 gas fees, and progress toward $2,000 USD target | M7 | Survey (R4) |
| F38 | Automated Verification & Test Non-Regression | Programmatic test execution across `tests/verify_live_terminal_metamask.py`, `simulation/paper_trader/evm_ten_trade_runner.py`, and full test suites | M7 | Survey (R4) |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M7 | Micro-Capital Compounding & MetaMask Execution to $2,000 USD | F31–F38: Dynamic sizing, micro-gas reserve, L2 routing, guardrail harmonization, autonomous compounding loop, telemetry tracking, and automated verification | None (Survey Complete) | IN_PROGRESS |

## Interface Contracts

### 1. Capital Sizing ↔ Execution Pipeline
```python
def calculate_micro_capital_sizing(wallet_balance_eth: float, eth_price_usd: float, adx_14: float) -> tuple[float, float]:
    """
    Returns (trade_usd, reserved_gas_eth).
    - reserved_gas_eth = min(0.0001, wallet_balance_eth * 0.08) (~$0.31 USD)
    - deployable_eth = max(0.0, wallet_balance_eth - reserved_gas_eth)
    - If total equity < $25: alloc_fraction = 0.85 if adx_14 >= 22.0 else 0.75
      trade_usd = round(deployable_eth * alloc_fraction * eth_price_usd, 2)
    - If total equity >= $25: transition to standard ATR-14 volatility sizing
    """
```

### 2. Guardrails Pipeline Micro-Capital Concentration
```python
class PreBroadcastGuardrailPipeline:
    def __init__(
        self,
        max_spend_per_trade_usd: float = 250.0,
        max_asset_concentration_pct: float = 20.0,
        max_daily_drawdown_pct: float = 8.0,
        eth_price_usd: float = 3100.0,
        allow_micro_capital_concentration: bool = True,
        ...
    ):
        ...
```
When `allow_micro_capital_concentration=True` and `current_portfolio_value_usd < 25.0`, concentration limit dynamically scales to `98.0%`, enabling single-position rotation on micro-capital balances.

### 3. Autonomous Compounding State Tracking
```python
bridge.wallet_balance_eth: float  # Synced from MetaMask (starting 0.0012 ETH)
bridge.cumulative_profit_usd: float  # Realized net PnL accumulated
bridge.target_profit_usd: float = 2000.0  # Compounding termination target
```
Loop continues while `cumulative_profit_usd < target_profit_usd` and does not halt on individual trade take-profit events.
