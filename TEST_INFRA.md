# Test Infrastructure & E2E Testing Architecture

## 1. System Overview & Testing Philosophy

The **Antigravity Agentic Trading Platform** is an institutional-grade, multi-agent automated cryptocurrency trading system. It orchestrates multi-agent market deliberations, dual-engine wallet execution, real-time visualization, and pre-broadcast safety guardrails.

Because this platform manages live financial assets on decentralized networks (Arbitrum One, Base), software correctness is safety-critical. Testing cannot be an afterthought or restricted to happy-path mocks. The E2E Testing Track is engineered as an **opaque-box, requirement-driven, independently verifiable test suite** governed by a **4-tier systematic testing methodology**.

---

## 2. 4-Tier Systematic Testing Methodology

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Tier 4: Real-World Scenarios                         │
│   (End-to-end full life-cycle workflows: Breakouts, Exits, Hedges)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│              Tier 3: Cross-Feature Pairwise Combinations               │
│   (Deliberation + Guardrails, Sizing + Quoter, Remote + Jev Scoring)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│               Tier 2: Boundary Value & Corner Cases                    │
│   (Max slippage, gas spikes, honeypots, rate limits, precision errors) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Tier 1: Feature Coverage                            │
│   (Category-Partition covering F01–F26, >=5 test cases per feature)    │
└────────────────────────────────────────────────────────────────────────┘
```

### Tier 1: Feature Coverage (Category-Partition)
- **Scope**: Every single feature in `PROJECT.md § Feature Inventory` (F01 through F26) is explicitly verified with $\ge 5$ distinct test cases.
- **Coverage**:
  - **F01–F07 (M1 Multi-Agent Architecture)**: Framework setup, Analyst teams, Bull/Bear debate, Risk Management debate, Trader proposal generation, Gemini/Antigravity integration, SQLite memory log persistence.
  - **F08–F14 (M2 Wallet & Safety Guardrails)**: Dual-engine wallet signer, Layer 1 Honeypot/Tax check, Layer 2 Capital allocation caps, Layer 3 Dynamic Uniswap slippage/price impact, Layer 4 Gas ceiling/ratio check, Layer 5 eth_call simulation, Multi-DEX routing.
  - **F15–F18 (M3 Trading Visualization & Jev)**: UI deployment & routes, SSE reasoning stream, WebSocket telemetry, Jev design quality gating (`jev_review_design`).
  - **F19–F23 (M4 Crypto Ingestion & Remote Agent)**: Multi-exchange CCXT feeds (BTC/ETH/SOL), ATR-14 volatility sizing, `agy --remote-agent` bridge, Production Buy/Sell/Hold recommendations, Jev heuristic scoring (`jev_decide`, `jev_pick_variant`).
  - **F24–F26 (M5 Backtest, Verification & Hardening)**: Multi-ticker paper trading grid runner, 100% E2E test suite validation, Tier 5 adversarial failure injection.
- **Minimum Tests**: $26 \times 5 = 130$ test cases.

### Tier 2: Boundary Value Analysis & Corner Cases
- **Scope**: Verifies all critical mathematical, network, and security boundaries where off-by-one errors or numerical instability could cause financial loss.
- **Key Boundary Categories**:
  1. *Dynamic Slippage & Price Impact*: 0 bps, 30 bps, 99 bps, 100 bps, 101 bps (rejection), and $>2.0\%$ price impact rejection.
  2. *Capital Caps & Drawdown Limits*: Per-trade cap at \$249.99 (allowed), \$250.00 (allowed), \$250.01 (rejected); 20% single-asset concentration threshold; 8.0% daily drawdown breaker trigger.
  3. *Gas Ceiling & Congestion*: Base fee at limit, base fee $>120$ gwei (blocked), gas-to-trade ratio at 1.49% (allowed), 1.50% (allowed), 1.51% (rejected).
  4. *Contract Honeypots & Taxes*: Buy tax 0.9% (allowed), 1.0% (allowed), 1.1% (rejected); unverified source code; honeypot flags.
  5. *Volatility & Lot Sizing Precision*: ATR-14 zero or negative values; fractional satoshi rounding; minimum exchange order size constraints.
  6. *Network & Stream Faults*: RPC connection timeouts, rate limit 429 backoff, truncated SSE chunk streams, WebSocket reconnect drops.

### Tier 3: Cross-Feature Pairwise Combinations
- **Scope**: Tests the interaction matrix between distinct subsystems to prevent interface mismatches and synchronization bugs:
  - `Agent Deliberation (M1)` $\leftrightarrow$ `Guardrail Pipeline (M2)`
  - `ATR Sizing Engine (M4)` $\leftrightarrow$ `Uniswap v3 Quoter (M2)`
  - `Remote Agent Deliberation (M4)` $\leftrightarrow$ `Jev Heuristic Decision Engine (M1/M4)`
  - `Execution Router (M2)` $\leftrightarrow$ `WebSocket / SSE Telemetry (M3)`
  - `Dual Chain Routing (Arbitrum vs Base)` $\leftrightarrow$ `Token Symbol Mapping (WETH, WBTC, SOL)`
  - `Simulation Reverts (M2)` $\leftrightarrow$ `Memory Log Rollback (M1)`

### Tier 4: Real-World Application Workloads
- **Scope**: Multi-step, realistic institutional trading lifecycles executed from raw market inputs to final settled balances:
  - **Scenario 1 — BTC Bull Breakout Trade**: Ingests Binance 1h OHLCV $\to$ Analyst team detects bullish momentum $\to$ Bull/Bear debate reaches 80% bull consensus $\to$ Trader proposes Buy at \$88,500 with stop-loss $\to$ Jev validates proposal $\to$ Guardrails L1–L5 pass $\to$ Arbitrum Uniswap v3 execution $\to$ SSE telemetry stream updates UI $\to$ Paper trading position logged.
  - **Scenario 2 — ETH Bear Breakdown Emergency Exit**: Alternative.me Fear & Greed drops to Extreme Fear (18) $\to$ News and Sentiment analysts flag market contagion $\to$ Bear researcher defeats Bull in 2 turns $\to$ Risk debaters agree on capital preservation $\to$ Trader proposes full Sell $\to$ Guardrails check gas $\to$ Base Aerodrome swap executes $\to$ Portfolio cash preserved.
  - **Scenario 3 — SOL Volatility Spike & Drawdown Hedge**: SOL 24h ATR surges 3x $\to$ Sizing engine cuts position sizing from 5% to 1.6% via ATR-14 $\to$ Daily portfolio drawdown reaches 7.9% $\to$ Breaker prevents further speculative entries $\to$ Hedge order proposed and verified.
  - **Scenario 4 — Remote Agent Cloud VM Fallback**: Primary cloud `agy --remote-agent` experiences simulated network timeout $\to$ System detects failure $\to$ Seamlessly falls back to local Antigravity Gemini client without data corruption.
  - **Scenario 5 — High Gas Congestion Deferral & Retry**: Layer 4 gas check trips during L2 congestion spike $\to$ Order enters queue $\to$ Gas normalizes $\to$ Pre-flight simulation re-runs $\to$ Order completes.

---

## 3. Interface Contracts & Schemas

The test suite enforces the exact Pydantic models defined in `PROJECT.md § Interface Contracts`:

1. **`TraderProposal`**:
   - `action`: `Literal["Buy", "Hold", "Sell"]`
   - `reasoning`: `str`
   - `entry_price`: `float | None`
   - `stop_loss`: `float | None`
   - `position_sizing`: `str | None`
   - `symbol`: `str`

2. **`PortfolioDecision`**:
   - `rating`: `Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]`
   - `executive_summary`: `str`
   - `investment_thesis`: `str`
   - `price_target`: `float | None`
   - `time_horizon`: `str | None`

3. **`GuardrailVerdict`**:
   - `approved`: `bool`
   - `rejection_reason`: `str | None`
   - `layer_failed`: `str | None`
   - `simulated_gas_used`: `int | None`
   - `quoted_amount_out_min`: `int | None`
   - `estimated_price_impact_pct`: `float | None`

4. **`AgentDeliberationEvent` (SSE Streaming)**:
   - `event`: `Literal["agent_thought", "debate_turn", "tool_call", "decision", "trade_telemetry"]`
   - `data`: Dict containing `agent_role`, `timestamp`, `token`, and `state_snapshot`.

5. **`CryptoRecommendation` (Remote Agent Output)**:
   - `symbol`: `str`
   - `rating`: `Literal["Buy", "Hold", "Sell"]`
   - `bull_argument`: `str`
   - `bear_argument`: `str`
   - `risk_assessment`: `str`
   - `position_size_usd`: `float`
   - `stop_loss_pct`: `float`

---

## 4. Test Infrastructure Architecture

```
tests/e2e/
├── __init__.py
├── conftest.py                   # Pytest fixtures, test hooks, isolation
├── contracts.py                  # Pydantic contract definitions
├── fixtures.py                   # High-fidelity offline mock adapters (RPC, GoPlus, CCXT, Jev)
├── harness.py                    # Unified testing harness & progressive adapter
├── test_tier1_f01_f07_multi_agent.py          # Tier 1: F01–F07 (M1 Multi-Agent)
├── test_tier1_f08_f14_wallet_guardrails.py    # Tier 1: F08–F14 (M2 Wallet & Guardrails)
├── test_tier1_f15_f18_visualization_jev.py    # Tier 1: F15–F18 (M3 UI & Jev Gating)
├── test_tier1_f19_f23_crypto_deliberation.py  # Tier 1: F19–F23 (M4 Crypto & Remote Agent)
├── test_tier1_f24_f26_simulation_hardening.py # Tier 1: F24–F26 (M5 Backtest & Hardening)
├── test_tier2_boundary_corner_cases.py        # Tier 2: Boundary Value Analysis
├── test_tier3_cross_feature_combinations.py   # Tier 3: Pairwise Combinations
├── test_tier4_real_world_scenarios.py         # Tier 4: Real-World Application Workloads
└── run_all.py                    # Standalone CLI test runner
```

### Determinism & Isolation
All tests execute **100% offline and deterministically**:
- External Web3 RPC nodes (Arbitrum, Base) are simulated via `MockWeb3Provider` with EVM state tracking and custom revert decoders.
- Security APIs (GoPlus) are mocked via `MockGoPlusClient` with configurable honeypot flags and tax percentages.
- Exchange APIs (CCXT Binance/Coinbase) are mocked via `MockCCXTExchange` returning deterministic OHLCV candles, ticker books, and precision truncation.
- Sentiment & Macro APIs (Alternative.me, DeFiLlama) are mocked via `MockPublicAPIs`.
- Google Antigravity & Gemini LLMs are mocked via `ScriptedLLMClient` with configurable response sequences, latency simulation, and token emission.
- Local Jev MCP engine is interfaced via `JevMCPTestAdapter` with deterministic fallback.

---

## 5. Execution Instructions

### Running via Pytest
```powershell
# Run the entire E2E test suite with verbose output
python -m pytest tests/e2e -v

# Run individual tiers
python -m pytest tests/e2e/test_tier1_*.py -v
python -m pytest tests/e2e/test_tier2_boundary_corner_cases.py -v
python -m pytest tests/e2e/test_tier3_cross_feature_combinations.py -v
python -m pytest tests/e2e/test_tier4_real_world_scenarios.py -v

# Run with summary and timings
python -m pytest tests/e2e --durations=10
```

### Running via Standalone Automated Runner
```powershell
# Execute all tiers and produce detailed terminal summary + test_results.json
python tests/e2e/run_all.py

# Filter by tier
python tests/e2e/run_all.py --tier 1
python tests/e2e/run_all.py --tier 2
python tests/e2e/run_all.py --tier 3
python tests/e2e/run_all.py --tier 4
```

---

## 6. Pass/Fail Semantics & Invalidation Conditions

1. **Pass Criteria**:
   - Every assertion across all 4 tiers must evaluate to `True`.
   - Zero unhandled exceptions or syntax errors.
   - 100% of test cases in the suite must pass (`0 failed, 0 errors`).
2. **Fail / Invalidation Conditions**:
   - Any assertion failure in guardrail threshold enforcement (e.g. trade allowed despite $>1\%$ tax or $>2\%$ slippage).
   - Any schema violation where `TraderProposal`, `PortfolioDecision`, or `GuardrailVerdict` fails Pydantic validation.
   - Any non-deterministic test failure caused by shared state or ordering dependencies.
