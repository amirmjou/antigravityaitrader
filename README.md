# Antigravity Agentic Trading Platform (`aitrader`)

Institutional-grade multi-agent trading deliberation, 6-layer pre-broadcast EVM safety guardrails, real-time SSE/WebSocket telemetry visualization, remote cloud deliberation, and MetaMask EVM airdrop/activity scanning.

- **Repository**: [https://github.com/amirmjou/aitrader](https://github.com/amirmjou/aitrader)

---

## Architecture Overview

1. **Core Multi-Agent Graph (`core/` — `v0.1.0`)**:
   - 10 specialized analyst, researcher (Bull/Bear debate), risk-debater, trader, and portfolio-manager agents orchestrated via LangGraph with SQLite checkpointing and Google Antigravity / Gemini LLM integration.
2. **EVM Execution & Pre-Broadcast Safety Guardrails (`execution/` — `v0.2.0`)**:
   - Dual-engine wallet (`eth-account` keystore signer + interactive EIP-1193 MetaMask bridge).
   - 6-layer pre-flight pipeline:
     1. GoPlus contract & honeypot verification
     2. Per-trade capital allocation & daily drawdown circuit breaker
     3. Uniswap v3 `IQuoterV2` slippage (`0.5%–1.0%`) & price-impact caps
     4. EIP-1559 gas ceiling & stuck-nonce speed-up/replacement handling
     5. Pre-broadcast `eth_call` & `eth_estimateGas` execution simulation
   - Multi-DEX swap routing on Arbitrum One (`42161`) and Base (`8453`) via Uniswap v3 `SwapRouter02` and Aerodrome.
3. **Real-Time Trading Visualization (`visualization/` — `v0.3.0`)**:
   - FastAPI SSE deliberation streaming (`agent_thought`, `debate_turn`, `tool_call`, `decision`) and WebSocket market/order-book telemetry.
4. **Crypto Deliberation & Remote Agent Bridge (`crypto_pipeline/` — `v0.4.0`)**:
   - CCXT OHLCV/order-book ingestion, Alternative.me Fear & Greed Index, DeFiLlama TVL feeds, ATR-14 volatility position sizing, and `agy --remote-agent` cloud deliberation bridge.
5. **Simulation, Backtesting & 5-Tier Verification (`simulation/`, `tests/` — `v1.0.0`)**:
   - Paper-trading order book matcher, multi-asset historical backtester, 200 opaque-box E2E tests (Tiers 1–4), and Tier 5 adversarial stress tests.
6. **Agentic Skills & MetaMask EVM Airdrop Scanner (`.agents/skills/`, `crypto_pipeline/airdrop_scanner.py` — `v1.1.0`)**:
   - First-class slash-command skills (`/trader-validation-pipeline`, `/airdrop-scan`, `/full-analysis`, `/stock-scan`, `/stock-data`, `/catalyst-check`, `/risk-score`, `/entry-exit`, `/new-session`, `/summary`).
   - Read-only multi-chain MetaMask `0x` activity scanner and live DefiLlama tokenless EVM protocol finder.

---

## Quickstart

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
pip install -e ".[dev]"
```

### 2. Run the Test Suites
```powershell
python -m pytest tests/test_airdrop_scanner.py -v
python -m pytest tests/unit/ -v
python -m pytest tests/e2e/ -v
```

### 3. Run the MetaMask EVM Airdrop & Activity Scanner
```powershell
# Scan a public 0x MetaMask address across Ethereum, Arbitrum, Base, Optimism, Linea, Scroll, ZKsync, and Sepolia
python -m crypto_pipeline.airdrop_scanner --address 0xYourPublicMetaMaskAddress --top 15 --export sessions/airdrop_report.md
```
