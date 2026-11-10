# Project: Antigravity Agentic Trading Platform

## Architecture
The Antigravity Agentic Trading Platform integrates institutional multi-agent deliberation, decentralized on-chain execution with strict pre-broadcast guardrails, real-time visualization, and remote cloud deliberation.

```
                              [Market Data Feeds]
                     (CCXT: BTC/ETH/SOL, DeFiLlama, Alt.me)
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │ Crypto Market Ingestion & Sizing  │ (Milestone 4)
                     │ (ATR-14 Volatility, Step Sizing)  │
                     └─────────────────┬─────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
   ┌───────────────────────────┐               ┌───────────────────────────┐
   │ TauricResearch/           │               │ Remote Agent Deliberation │
   │ TradingAgents Graph       │ (Milestone 1) │ (agy --remote-agent)      │ (Milestone 4)
   │ - Analyst Teams           │               │ Cloud VM Deliberation     │
   │ - Bull/Bear Debate        │               │ Structured JSON Output    │
   │ - Risk Management Debate  │               └─────────────┬─────────────┘
   │ - Portfolio & Trader      │                             │
   └─────────────┬─────────────┘                             │
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       │ Structured Recommendations
                                       │ (TraderProposal / PortfolioDecision)
                                       ▼
                     ┌───────────────────────────────────┐
                     │ Jev Deterministic Scoring Engine  │ (Milestone 1 & 4)
                     │ (jev_decide & jev_pick_variant)   │
                     └─────────────────┬─────────────────┘
                                       │ Verified Order Parameters
                                       ▼
                     ┌───────────────────────────────────┐
                     │ Pre-Broadcast Safety Pipeline     │ (Milestone 2)
                     │ 1. GoPlus Contract & Honeypot     │
                     │ 2. Allocation & Drawdown Caps     │
                     │ 3. IQuoterV2 Slippage & Impact    │
                     │ 4. Gas Ceiling & Ratio Filter     │
                     │ 5. eth_call Pre-Flight Simulation │
                     └─────────────────┬─────────────────┘
                                       │ Approved Transactions
                                       ▼
                     ┌───────────────────────────────────┐
                     │ Dual-Engine Execution Router      │ (Milestone 2)
                     │ - Local Keystore Signer (Auto)    │
                     │ - EIP-1193 MetaMask Bridge (UI)   │
                     │ - Uniswap v3 / Aerodrome on L2    │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼ On-Chain Settlement / Telemetry
                     ┌───────────────────────────────────┐
                     │ Trading Visualization Interface   │ (Milestone 3)
                     │ - SSE Deliberation Streaming      │
                     │ - WebSocket Market Charts         │
                     │ - Jev Design Quality Gate         │
                     └───────────────────────────────────┘
```

---

## Feature Inventory
Every feature identified during Phase 0 Survey is cataloged below with its designated milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Framework Setup & Dependencies | Clone, install, and configure TauricResearch/TradingAgents with Python 3.11 environment | M1 | Survey 1 (R1) |
| F02 | Analyst Team Architecture | Market, Sentiment, News, Fundamentals analysts in isolated subgraphs with bounded tool loops | M1 | Survey 1 (R1) |
| F03 | Bull/Bear Researcher Debate | Dynamic multi-turn Bull vs. Bear debate with Research Manager consensus synthesis | M1 | Survey 1 (R1) |
| F04 | Risk Management Debaters | Aggressive, Conservative, and Neutral risk debate adjudicated by Portfolio Manager | M1 | Survey 1 (R1) |
| F05 | Trader Agent Proposal Engine | Strategic plan and technical level conversion into explicit TraderProposal (entry, stop, size) | M1 | Survey 1 (R1) |
| F06 | Antigravity & Gemini Integration | Integration with NormalizedChatGoogleGenerativeAI, Google Antigravity SDK, and thinking levels | M1 | Survey 1 (R1) |
| F07 | Memory & Reflection Settlement | SQLite checkpointing, TradingMemoryLog persistence, and benchmark alpha settlement | M1 | Survey 1 (R1) |
| F08 | Dual-Engine Wallet Architecture | Autonomous eth-account hot-wallet signer + interactive EIP-1193 MetaMask web bridge | M2 | Survey 2 (R2) |
| F09 | Guardrail L1: Contract Security | GoPlus API honeypot detection, mintable verification, and buy/sell tax <=1% check | M2 | Survey 2 (R2) |
| F10 | Guardrail L2: Capital Allocation | Hard per-trade spend cap ($250 default), 20% max asset concentration, 8% daily drawdown breaker | M2 | Survey 2 (R2) |
| F11 | Guardrail L3: Dynamic Slippage | Uniswap v3 IQuoterV2 off-chain pricing, 30-100 bps slippage, <=2% price impact, 300s deadline | M2 | Survey 2 (R2) |
| F12 | Guardrail L4: Gas & Congestion | EIP-1559 base fee check, priority fee cap, and gas-cost-to-trade ratio <=1.5% ceiling | M2 | Survey 2 (R2) |
| F13 | Guardrail L5: Pre-Flight Simulation | eth_call dry-run on live state with custom revert reason decoding | M2 | Survey 2 (R2) |
| F14 | Multi-DEX Execution Router | Swap execution on Arbitrum One (42161) and Base (8453) via Uniswap v3 SwapRouter02 & Aerodrome | M2 | Survey 2 (R2) |
| F15 | Visualization UI Deployment | Deploy and configure open-source trading UI (HKUDS/Vibe-Trading / NoFxAiOS/nofx) | M3 | Survey 3 (R3) |
| F16 | Real-Time Reasoning Streaming | Dual-channel SSE (deliberation tokens, tool calls, debate transcripts) and WebSockets (telemetry) | M3 | Survey 3 (R3) |
| F17 | Interactive Market & Chart Telemetry | Live K-line candles, technical indicators, trade execution markers, and order book depth | M3 | Survey 3 (R3) |
| F18 | Jev Design Quality Gating | UI visual hierarchy, page fidelity, and consistency validation via jev_review_design | M3 | User Follow-up |
| F19 | Crypto Data Ingestion Feeds | CCXT multi-exchange data (OHLCV, Order Book), Alternative.me (Fear & Greed), DeFiLlama (TVL) | M4 | Survey 3 (R4) |
| F20 | Volatility-Adjusted Sizing | ATR-14 fixed-fractional risk allocation and exchange.amount_to_precision lot sizing | M4 | Survey 3 (R4) |
| F21 | Remote Agent Deliberation Bridge | agy --remote-agent non-interactive execution with structured JSON recommendation parsing | M4 | Survey 3 (R4) |
| F22 | Production Crypto Recommendations | Explicit Buy/Sell/Hold ratings, Bull vs Bear arguments, risk assessments for BTC, ETH, SOL | M4 | Survey 3 (R4) |
| F23 | Jev Deterministic Decision Scoring | Deterministic heuristic scoring of trade strategies via jev_decide and jev_pick_variant | M4 | User Follow-up |
| F24 | Automated Backtest & Paper Trading | Multi-ticker, multi-date grid runner and paper trading simulation validating end-to-end dataflow | M5 | Verification (R1-R4) |
| F25 | 100% E2E Verification (Tiers 1-4) | Comprehensive opaque-box test suite execution passing 100% across all 4 tiers | M5 | Dual Track Gate |
| F26 | Tier 5 Adversarial Hardening | White-box adversarial stress testing, failure injection, and coverage audit | M5 | Dual Track Phase 2 |
| F27 | Live Terminal Server & Token Auth Gate | `run_live_metamask_terminal.py` on port 8899, token auth enforcement on GET `/` returning 200 with token, 401 without | M6 | Live Dispatch (R1) |
| F28 | Multi-Asset Spot Telemetry & Indicators | Real-time BTC, ETH, SOL spot prices, RSI, ADX, SMA/EMA, MACD, and order book over `/ws/telemetry` | M6 | Live Dispatch (R2) |
| F29 | MetaMask EIP-1193 Bridge Endpoints | `/wallet_syncAccount`, `/rpc`, `/send-transaction`, `/confirm-transaction` with guardrail validation & reject handling | M6 | Live Dispatch (R3) |
| F30 | Automated Verification & Non-Regression | Programmatic automated test harness `tests/verify_live_terminal_metamask.py` and full test suite non-regression | M6 | Live Dispatch (R4) |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Independent opaque-box test suite (Tiers 1-4, test runner, TEST_READY.md) | None (Parallel Track) | DONE (TEST_READY.md published, 200/200 passed) |
| M1 | Multi-Agent Architecture Integration | F01–F07: Clone & install TradingAgents, configure 10-agent hierarchy, LangGraph, Gemini & Jev | None | DONE (1420 core, 52 adversarial, 200 E2E passed; Gate APPROVED) |
| M2 | MetaMask Wallet & Safety Guardrails | F08–F14: Dual-engine wallet, 6-layer pre-broadcast safety pipeline, DEX router, simulation | M1 (Interface Contracts) | DONE (173 adversarial, 35 unit, 35 Tier 1, 200 E2E, 1420 core passed; Gate APPROVED) |
| M3 | Trading Visualization Interface | F15–F18: Deploy UI, SSE reasoning stream, WebSocket telemetry, Jev design review gate | M1, M2 | DONE (33 unit, 10 Jev, 20 Tier 1, 200 E2E passed; Gate APPROVED) |
| M4 | Crypto Deliberation & Remote Agent | F19–F23: BTC/ETH/SOL ingestion, ATR sizing, agy --remote-agent bridge, Jev decision scoring | M1, M2 | DONE (Full CCXT/FNG/DeFiLlama feeds, ATR-14 sizer, remote bridge, Jev scorer passed; Gate APPROVED) |
| M5 | Final Milestone: E2E Verification & Hardening | F24–F26: Pass 100% E2E test suite (Tiers 1-4), paper trading backtest, Tier 5 adversarial hardening | E2E, M1, M2, M3, M4 | DONE (200/200 E2E, 1420/1420 Core, Unit & Adversarial suites passed; Gate APPROVED) |
| M6 | Live Terminal & MetaMask Bridge Deployment | F27–F30: Live terminal on port 8899, token auth gate, telemetry WS, reasoning SSE, bridge routes, and verification harness | M1–M5 | DONE (477+ tests passing across 6 suites; Gate APPROVED) |

---

## Interface Contracts

### 1. Multi-Agent Graph (M1) ↔ Execution Guardrails (M2)
- **Data Model**: `TraderProposal` & `PortfolioDecision`
```python
class TraderProposal(BaseModel):
    action: Literal["Buy", "Hold", "Sell"]
    reasoning: str
    entry_price: float | None
    stop_loss: float | None
    position_sizing: str | None
    symbol: str

class PortfolioDecision(BaseModel):
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    executive_summary: str
    investment_thesis: str
    price_target: float | None
    time_horizon: str | None
```
- **Semantics**: M1 emits typed proposals. M2 parses `action`, `entry_price`, and `stop_loss` to calculate token amounts and construct swap transactions.

### 2. Guardrails (M2) ↔ Execution Routers
- **Guardrail Decision Model**: `GuardrailVerdict`
```python
class GuardrailVerdict(BaseModel):
    approved: bool
    rejection_reason: str | None = None
    layer_failed: str | None = None
    simulated_gas_used: int | None = None
    quoted_amount_out_min: int | None = None
    estimated_price_impact_pct: float | None = None
```
- **Semantics**: If `approved == False`, transaction broadcast is hard-blocked and logged.

### 3. Agent & Market Pipeline (M1, M4) ↔ Visualization UI (M3)
- **Event Streaming Contract**: `AgentDeliberationEvent` (SSE format)
```json
{
  "event": "agent_thought" | "debate_turn" | "tool_call" | "decision" | "trade_telemetry",
  "data": {
    "agent_role": "Bull Researcher" | "Bear Researcher" | "Portfolio Manager" | "Market Analyst",
    "timestamp": "2026-11-06T15:55:00Z",
    "token": "...",
    "state_snapshot": { ... }
  }
}
```

### 4. Decision Pipeline ↔ Jev Local Heuristic Engine
- **Jev MCP Tools**: `jev_decide`, `jev_pick_variant`, `jev_review_design`
- **Semantics**:
  - `jev_decide`: Deterministic heuristic scoring for risk consensus and trade approval.
  - `jev_pick_variant`: Scoring multiple bull/bear trade variants.
  - `jev_review_design`: UI layout fidelity and visual hierarchy quality gate for M3.

---

## Code Layout
```
c:\Users\AmirM\Documents\Agentic trading\
├── PROJECT.md                  # Project index & architecture (this file)
├── TEST_INFRA.md               # E2E Test Track index & test architecture
├── TEST_READY.md               # E2E Test Suite readiness declaration
├── DEAD_ENDS.md                # Oscillation guard & dead end tracking
├── GATE_STATUS.md              # Gate verdict tracking per iteration
│
├── core/                       # Core TradingAgents integration (M1)
│   ├── agents/                 # 10 specialized agent roles across 4 tiers
│   ├── graph/                  # LangGraph state machine, conditional logic, checkpointer
│   ├── llm_clients/            # Gemini & Antigravity SDK LLM abstractions
│   ├── dataflows/              # Vendor data retrieval & crypto symbol normalization
│   └── memory/                 # Decision logging & reflection engine
│
├── execution/                  # Execution & Safety Guardrails (M2)
│   ├── guardrails/             # 6-layer pre-broadcast safety pipeline (GoPlus, Caps, Slippage, Gas, Simulation)
│   ├── wallet/                 # Dual-engine wallet (eth-account hot keystore + EIP-1193 bridge)
│   └── routers/                # Uniswap v3 & Aerodrome swap routers (Arbitrum, Base)
│
├── visualization/              # Trading Visualization Interface (M3)
│   ├── web/                    # Frontend UI (HKUDS/Vibe-Trading / NoFxAiOS/nofx adapter)
│   ├── server/                 # FastAPI SSE & WebSocket streaming server
│   └── telemetry/              # Trade & agent telemetry collectors
│
├── crypto_pipeline/            # Crypto Deliberation & Remote Agent (M4)
│   ├── ingestion/              # CCXT, Alternative.me, DeFiLlama market feeds (BTC, ETH, SOL)
│   ├── sizing/                 # ATR-14 fixed-fractional volatility sizing & step rounding
│   ├── remote_agent/           # agy --remote-agent CLI execution bridge
│   └── jev_integration/        # Jev heuristic decision & variant scoring adapter
│
├── simulation/                 # Backtesting & Paper Trading (M5)
│   ├── paper_trader/           # Simulated exchange order matching & portfolio book
│   └── backtester/             # Multi-asset historical backtest grid runner
│
└── tests/                      # E2E & Unit Test Suites (Dual Track & All Modules)
    ├── e2e/                    # Opaque-box E2E test suite (Tiers 1-4)
    ├── adversarial/            # Tier 5 Adversarial test cases
    └── unit/                   # Component unit test suites
```
