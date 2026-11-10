# Changelog

All notable changes to the **Antigravity Agentic Trading Platform (`aitrader`)** are documented in this file.

## [v1.1.0] - 2026-11-08
### Added
- **MetaMask EVM Airdrop & On-Chain Activity Scanner** (`crypto_pipeline/airdrop_scanner.py`):
  - Multi-chain balance & nonce scanner across Ethereum, Arbitrum, Base, Optimism, Linea, Scroll, ZKsync Era, and Sepolia Testnet.
  - Anti-Sybil & Airdrop Readiness Score (`0–100`) with paste-to-check links (`Drops.bot`, `DeBank`, `Blockscan`, `Revoke.cash`).
  - Live DefiLlama API integration filtering high-TVL tokenless EVM protocols.
- **Agentic Skills** (`.agents/skills/` & `.agent/skills/`):
  - Added `/trader-validation-pipeline` multi-agent copy-trading validation skill.
  - Added `/airdrop-scan` MetaMask wallet & tokenless protocol scanning skill.
  - Migrated all 8 legacy stock analysis workflows (`catalyst-check`, `entry-exit`, `full-analysis`, `new-session`, `risk-score`, `stock-data`, `stock-scan`, `summary`) to modern `SKILL.md` format.

## [v1.0.0] - 2026-11-07
### Added
- **Simulation & Paper Trading (`simulation/`)**:
  - Simulated exchange order matching and multi-asset historical backtest grid runner.
- **End-to-End & Adversarial Verification (`tests/`)**:
  - 200/200 opaque-box E2E tests across Tiers 1–4 (`tests/e2e/`).
  - Tier 5 adversarial hardening and failure-injection suites (`tests/adversarial/`).

## [v0.4.0] - 2026-11-07
### Added
- **Crypto Deliberation & Remote Agent Pipeline (`crypto_pipeline/`)**:
  - `CCXTMarketFeed`, `AlternativeMeFearGreedFeed`, and `DeFiLlamaTVLFeed`.
  - `ATRSizingEngine` for ATR-14 fixed-fractional volatility sizing and exchange step rounding.
  - `RemoteAgentDeliberationBridge` for `agy --remote-agent` cloud deliberation.
  - `JevCryptoDecisionScorer` for deterministic heuristic trade scoring.

## [v0.3.0] - 2026-11-06
### Added
- **Trading Visualization Interface (`visualization/`)**:
  - FastAPI SSE deliberation streaming and WebSocket market/order-book telemetry server.
  - Web frontend adapter and telemetry collectors.

## [v0.2.0] - 2026-11-06
### Added
- **EVM Execution Router & 6-Layer Pre-Broadcast Guardrails (`execution/`)**:
  - Dual-engine wallet (`eth-account` hot keystore + interactive EIP-1193 MetaMask bridge).
  - GoPlus contract security check, capital allocation/drawdown caps, Uniswap v3 `IQuoterV2` slippage check, EIP-1559 gas ceiling, and `eth_call` pre-flight simulation.
  - Swap routers for Uniswap v3 and Aerodrome on Arbitrum One and Base.

## [v0.1.0] - 2026-11-06
### Added
- **Core Multi-Agent Trading Graph (`core/`)**:
  - 10-agent hierarchy (Market, Sentiment, News, Fundamentals Analysts; Bull/Bear Researchers; Risk Debaters; Trader & Portfolio Manager).
  - LangGraph state machine, SQLite checkpointing, and Google Antigravity / Gemini LLM clients.
