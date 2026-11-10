# Technical Survey Report: Trading Visualization UIs & Remote Agent Deliberation Pipeline

**Author**: `teamwork_explorer_survey_3`  
**Date**: 2026-11-06  
**Context**: Agentic Trading System Architecture  
**Scope**: Requirements R3 (Trading Visualization Interface) & R4 (Cryptocurrency Analysis & Remote Agent Recommendation Pipeline)

---

## 1. Executive Summary

This report evaluates candidate open-source trading visualization interfaces and architects the remote crypto deliberation pipeline connecting **TauricResearch/TradingAgents** with **Google Antigravity CLI (`agy --remote-agent`)** across major cryptocurrencies (**BTC, ETH, and SOL**).

### Key Findings & Recommendations:
1. **Visualization UI Recommendation**:
   - **Primary Recommendation: HKUDS/Vibe-Trading** (`HKUDS/Vibe-Trading`).  
     *Rationale*: 100% Python/FastAPI backend aligned directly with `TradingAgents` (LangGraph/LangChain), unified single Docker container on port `8899`, native Server-Sent Events (SSE) streaming for agent thought tokens and 68+ tool execution inspection, and persistent session checkpoints.
   - **Specialized Alternative: NoFxAiOS/nofx** (`NoFxAiOS/nofx`).  
     *Rationale*: Best-in-class dedicated crypto terminal UX with an "AI Debate Arena" (Bull vs. Bear side-by-side view), interactive K-line charting with entry plans, and "Frontier Mode" (human-in-the-loop order approval). Because its backend is Go/SQLite, it requires a lightweight FastAPI proxy bridge to consume Python `TradingAgents` reasoning streams.
   - **Deprioritized: OpenByteInc/QuantDinger** (`OpenByteInc/QuantDinger`).  
     *Rationale*: Enterprise SaaS OS introducing excessive infrastructure overhead (Kafka, Redis, PostgreSQL, Celery workers, Prometheus/Grafana) without native multi-agent LLM debate stream visualization.

2. **`agy --remote-agent` Integration**:
   - Non-interactive, machine-readable execution is achieved using:
     ```bash
     agy --remote-agent -p "<prompt>" --output-format json
     ```
     For real-time token/event streaming, `--output-format stream-json` provides Newline-Delimited JSON (NDJSON).
   - Headless scripts can pipe live market data and multi-agent debate prompts directly into `agy`, capturing turn duration, tokens, and structured trade recommendations without local GPU/CPU compute constraints.

3. **Crypto Deliberation Pipeline (BTC, ETH, SOL)**:
   - Ingestion: Multi-source feed combining **CCXT** (Binance/Coinbase/Kraken OHLCV & L2 Order Book), **DeFiLlama** (Chains TVL, DEX volume), and **Alternative.me** (Crypto Fear & Greed Index).
   - Sizing & Safeguards: Fixed-fractional risk allocation constrained by ATR volatility-based stop-loss distances, exchange precision rounding (`exchange.amount_to_precision`), and hard notional portfolio caps (max 10%).

---

## 2. In-Depth Evaluation of Trading Visualization UI Candidates (Requirement R3)

### 2.1 Candidate 1: HKUDS/Vibe-Trading (`HKUDS/Vibe-Trading`)
- **Origin & Architecture**: Developed by the Data Intelligence Lab at the University of Hong Kong (HKUDS). Decoupled architecture with a **FastAPI** backend orchestrating multi-agent LLM workflows (LangGraph/LangChain) and a modern **React (Vite + React 19)** frontend dashboard.
- **Dependencies**: Python 3.10+, FastAPI, Pydantic, Uvicorn, LangChain/LangGraph, Node.js 18+.
- **Ease of Deployment**: **High**. A single Docker image (`docker compose up --build`) launches the complete frontend + backend unified on port `8899`. Persistent state and memory are retained via Docker named volumes.
- **Real-Time Agent Reasoning Streaming**: **Native SSE (Server-Sent Events)**. Streams token-by-token LLM thoughts, multi-agent status transitions, and tool calls (68+ financial analysis tools) directly to the web client. Includes connection interruption recovery and checkpoint persistence.
- **Market Data Chart Integration**: Includes interactive charting, alpha factor visualization ("Alpha Zoo"), backtesting equity curves, and multi-asset data ingestion fallbacks.
- **Telemetry Display**: Detailed execution ledgers, tool call logs, risk management parameters, shadow portfolio tracking, and broker execution state.
- **System Synergy**: Highest synergy with `TauricResearch/TradingAgents`. Both are native Python/LangGraph systems, enabling direct in-process or API-level integration without language bridges.

---

### 2.2 Candidate 2: NoFxAiOS/nofx (`NoFxAiOS/nofx`)
- **Origin & Architecture**: Purpose-built open-source AI trading operating system and terminal assistant. Backend written in **Go**, frontend in **React / TypeScript**, backed by an embedded **SQLite** database.
- **Dependencies**: Go 1.21+, Node 18+, TA-Lib (C library or wrapper), SQLite.
- **Ease of Deployment**: **High**. Distributed via a clean 2-container Docker Compose setup (`docker compose -f docker-compose.prod.yml up -d`) exposing the React/Nginx frontend on port `3000` with an internal Go microservice.
- **Real-Time Agent Reasoning Streaming**: **Exceptional**. Parses structured `<reasoning>` thought tags, displays real-time decision logs, and features a specialized **"AI Debate Arena"** where multiple models pitch bull vs. bear arguments side-by-side.
- **Market Data Chart Integration**: High-performance interactive K-line charts featuring multi-timeframe OHLCV, indicator overlays (EMA 20/50/200, MACD, RSI, ATR), live order book depth, open interest (OI) shifts, funding rates, institutional fund flows, and visual entry/ladder/TWAP order markers.
- **Telemetry Display**:
  - *Frontier Mode*: Interactive chat + live chart enabling human traders to co-pilot trades with the AI, review planned entries, and manually approve orders before broadcast.
  - *Autopilot Mode*: Continuous automated trading, equity curve tracking, open positions, real-time P&L, and Go-enforced hard risk limits.
- **System Synergy**: Frontend and UI/UX are ideal for crypto trading, but the Go backend requires a lightweight FastAPI adapter service to ingest Python `TradingAgents` reasoning events.

---

### 2.3 Candidate 3: OpenByteInc/QuantDinger (`OpenByteInc/QuantDinger`)
- **Origin & Architecture**: Local-first AI quantitative trading operating system designed for Python strategy authors and multi-tenant SaaS. Highly distributed microservices stack: Python API backend, Vue 3 (Ant Design Vue) frontend, Celery workers, Kafka message broker, Redis caching/queues, PostgreSQL database, and optional Prometheus/Grafana monitoring.
- **Dependencies**: Python 3.10+, Vue 3, Vite, pnpm, Docker Compose v2, Kafka, Redis, PostgreSQL, Celery, Pyodide (WASM Python).
- **Ease of Deployment**: **Low / Heavyweight**. Requires orchestrating 6+ interconnected containers, database schema migration jobs, and Kafka topic initializations. Requires multi-gigabyte RAM allocation and significant operational maintenance.
- **Real-Time Agent Reasoning Streaming**: WebSocket and Kafka messaging bus, but optimized for quantitative tick events, strategy execution state machines, and backtest results rather than interactive conversational debate streaming.
- **Market Data Chart Integration**: Uses KLineCharts and ECharts for candlestick rendering, alongside in-browser Monaco/CodeMirror Python code editors.
- **Telemetry Display**: Multi-tenant SaaS dashboards, billing, account management, portfolio equity curves, and execution logs.
- **System Synergy**: Over-engineered for a focused trading agent terminal; unnecessary operational overhead for integrating `TradingAgents`.

---

### 2.4 Comparative Evaluation Matrix

| Evaluation Dimension | HKUDS/Vibe-Trading | NoFxAiOS/nofx | OpenByteInc/QuantDinger |
| :--- | :--- | :--- | :--- |
| **Backend Language** | Python (FastAPI) | Go (Go 1.21+) | Python + Celery |
| **Frontend Framework** | React (Vite / React 19) | React + TypeScript | Vue 3 + Ant Design |
| **Database / Persistence** | SQLite / Local Volume | SQLite | PostgreSQL |
| **Container Footprint** | 1 Container (Port 8899) | 2 Containers (Port 3000) | 6+ Containers (Kafka, Redis, Postgres, Workers) |
| **Resource Usage** | Lightweight (~400MB RAM) | Ultra-lightweight (~250MB RAM) | Heavyweight (3GB+ RAM) |
| **Agent Thought Streaming** | Native SSE token/tool stream | Native `<reasoning>` & Debate Arena | WebSockets / Kafka event bus |
| **Crypto Indicators & OI** | Standard financial charts | Full crypto perp metrics (OI, Funding, L/S) | Standard KLineCharts / ECharts |
| **Human-in-the-Loop** | Yes (interactive prompt/review) | Yes (**Frontier Mode** with trade approval) | Script execution approval |
| **TauricResearch Integration** | **Direct native Python/LangGraph** | Requires FastAPI REST/SSE adapter | Complex Celery/Kafka worker adapter |
| **Overall Score (1-10)** | **9.2 / 10** | **9.0 / 10** | **5.5 / 10** |

### 2.5 UI Recommendation Conclusion
- **Primary Selection**: **HKUDS/Vibe-Trading** is the recommended default because of its zero-friction Python compatibility with `TauricResearch/TradingAgents`, single-container simplicity, and native SSE streaming.
- **Alternative Selection**: If the user desires the specialized **"AI Debate Arena"** and **"Frontier Mode"** order approval dashboard, **NoFxAiOS/nofx** is selected with a lightweight FastAPI proxy translating `TradingAgents` events into NOFX's REST/WebSocket format.

---

## 3. `agy --remote-agent` Architecture & CLI Execution Mechanics (Requirement R4)

### 3.1 Overview & Capabilities
`agy --remote-agent` is a native execution capability of the Google Antigravity CLI (v1.4.12+) that offloads agent task execution into an **isolated, Google-managed cloud VM environment**.
- **Cloud Isolation**: Execution runs in Google Cloud infrastructure, preserving local CPU/RAM resources and persisting long-running deliberation tasks even if local terminals disconnect.
- **Authentication**: Requires a Google AI Pro or Ultra subscription.
- **Remote Workspace Resources**: Remote agents can mount git repositories, cloud drive folders, and execute shell tools inside the sandboxed VM.

### 3.2 CLI Syntax & Parameters

| Flag | Parameter / Format | Description |
| :--- | :--- | :--- |
| `--remote-agent` | *None* | Offloads execution to the Google-managed remote cloud VM. |
| `-p` / `--prompt` / `--print` | `"<prompt_string>"` | Non-interactive / headless single-turn execution mode. Exits after task completion. |
| `--output-format` | `text \| json \| stream-json` | Formatting for stdout. `json` yields a structured result object; `stream-json` yields real-time NDJSON events. |
| `--project` | `<project-id-or-name>` | Attaches session to an existing remote project environment. |
| `--new-project` | *None* | Provisions a new isolated remote project workspace. |
| `--mode` | `auto \| accept-edits \| plan` | Autonomy tier for tool executions. |
| `--dangerously-skip-permissions` | *None* | Bypasses interactive confirmation prompts for non-protected tool executions. |

### 3.3 Machine-Readable Input & Output Schemas

#### Invocation Command:
```bash
agy --remote-agent \
    --project crypto-deliberation \
    --output-format json \
    --dangerously-skip-permissions \
    -p "Deliberate trading decision for BTC/USDT using attached market payload."
```
Alternatively, piping structured context via `stdin`:
```bash
cat market_context_btc.json | agy --remote-agent --output-format json -p "Execute institutional trading deliberation."
```

#### Output Schema (`--output-format json`):
Standard diagnostic messages are routed to `stderr`, keeping `stdout` clean for JSON parsing:
```json
{
  "status": "success",
  "turn_count": 4,
  "duration_ms": 8420,
  "token_usage": {
    "prompt_tokens": 3410,
    "completion_tokens": 890,
    "thinking_tokens": 1240,
    "total_tokens": 5540
  },
  "response": {
    "symbol": "BTC/USDT",
    "timestamp": "2026-11-06T15:45:00Z",
    "action": "BUY",
    "confidence": 0.82,
    "deliberation": {
      "bull_case": "Price holds EMA(50) support at $96,200; positive exchange net outflows; Funding rate normalized at 0.008%.",
      "bear_case": "Overhead resistance at $98,500; RSI(14) approaching 68 on 4h timeframe.",
      "debate_synthesis": "Bullish momentum confirmed by high volume breakout above local VWAP; risk/reward ratio of 2.67 justifies entry."
    },
    "risk_assessment": {
      "volatility_regime": "NORMAL",
      "atr_14": 1420.50,
      "invalidation_stop_loss": 95100.00,
      "take_profit_targets": [98400.00, 101200.00]
    },
    "order_sizing": {
      "target_entry_price": 96850.00,
      "position_size_usd": 1000.00,
      "base_quantity": 0.01032,
      "max_slippage_pct": 0.5,
      "gas_threshold_usd": 25.00
    }
  }
}
```

### 3.4 Bridging TradingAgents to `agy --remote-agent`
Three architectural patterns can bridge `TauricResearch/TradingAgents` with `agy --remote-agent`:

1. **Pattern A: External Coordinator Bridge (Recommended)**:
   - A local Python pipeline ingests real-time crypto data (CCXT, DeFiLlama, Alternative.me).
   - The coordinator formats a multi-perspective context prompt containing analyst findings.
   - It invokes `agy --remote-agent -p ... --output-format json` as a headless subprocess.
   - The remote agent performs deep institutional synthesis (Debate & Risk Management) using Google's hosted models in the cloud VM.
   - The returned JSON recommendation is parsed, verified by local MetaMask safety guardrails, and sent to the visualization UI.

2. **Pattern B: Cloud-Resident Swarm Workspace**:
   - `TauricResearch/TradingAgents` is installed directly inside the remote agent cloud workspace (`--project crypto-deliberation`).
   - The CLI command invokes the deliberation script inside the VM:
     ```bash
     agy --remote-agent --project crypto-deliberation -p "python run_deliberation.py --symbol ETH/USDT" --output-format stream-json
     ```
   - Cloud VM executes the LangGraph multi-agent loop directly and streams NDJSON events back to the local daemon.

3. **Pattern C: Hybrid SDK Bridge (`google.antigravity`)**:
   - TradingAgents graph nodes run locally, but dispatch compute-intensive debate steps (Bull Researcher, Bear Researcher, Risk Arbiter) via the Python `google.antigravity` SDK using `LocalAgentConfig` / `InteractionsConnection`.

---

## 4. Cryptocurrency Market Recommendation Pipeline (BTC, ETH, SOL) (Requirement R4)

### 4.1 Multi-Source Data Feeds

| Data Domain | Target Assets | Provider / API | Frequency | Metrics Extracted |
| :--- | :--- | :--- | :--- | :--- |
| **Market Tickers & OHLCV** | BTC, ETH, SOL | **CCXT** (Binance, Coinbase, Kraken) | 1s ticker, 1m/15m/1h/4h/1d candles | Open, High, Low, Close, Volume, VWAP |
| **Market Depth (L2)** | BTC, ETH, SOL | **CCXT** `fetch_order_book()` | 5s / on-demand | Top 20 bids/asks, Bid-Ask Spread, Depth Imbalance |
| **Technical Indicators** | BTC, ETH, SOL | `pandas-ta` / native calculation | Calculated per candle | EMA(20/50/200), MACD, RSI(14), ATR(14), BB(20,2) |
| **Derivatives Metrics** | BTC, ETH, SOL | Binance Futures / Coinglass | 1m - 5m | Open Interest (OI), Funding Rates, Long/Short Ratio |
| **On-Chain Fundamentals** | BTC | Blockchain.com / Glassnode | Hourly / Daily | Hashrate, Exchange Netflows, MVRV Ratio |
| **On-Chain Fundamentals** | ETH | Etherscan / DeFiLlama | Real-time / Hourly | Gas Base Fee (Gwei), Validator Staking Yield, L2 TVL |
| **On-Chain Fundamentals** | SOL | Solscan / DefiLlama | Real-time / Hourly | TPS, DEX Trading Volume (Raydium/Orca), Priority Fees |
| **Macro Sentiment** | All Crypto | **Alternative.me** (`/fng/`) | Daily / Hourly | Fear & Greed Index score (0-100) & classification |

### 4.2 Mathematical Order Sizing & Risk Parameters
To safeguard institutional capital, position sizing is calculated using **Fixed-Fractional Volatility Risk Budgeting**:

1. **Dollar Risk Budget**:
   $$\text{Risk Budget} = \text{Portfolio USD} \times \text{Risk Per Trade \% (e.g. 1\%)}$$
2. **Unit Stop-Loss Distance (based on ATR)**:
   $$\text{Stop Distance} = \max(\text{Entry Price} - \text{Stop Loss Price}, 1.5 \times \text{ATR}_{14})$$
3. **Raw Position Quantity**:
   $$\text{Raw Quantity} = \frac{\text{Risk Budget}}{\text{Stop Distance}}$$
4. **Hard Notional Cap Enforcement**:
   $$\text{Notional Value} = \min(\text{Raw Quantity} \times \text{Entry Price}, \text{Portfolio USD} \times \text{Max Notional \% (e.g. 10\%)})$$
   $$\text{Adjusted Quantity} = \frac{\text{Notional Value}}{\text{Entry Price}}$$
5. **Exchange Precision Adjustment**:
   $$\text{Final Order Amount} = \text{exchange.amount\_to\_precision}(\text{symbol}, \text{Adjusted Quantity})$$

### 4.3 Python Implementation Blueprint

```python
import ccxt
import requests
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# 1. Pydantic Structured Output Schema
class DeliberationDebate(BaseModel):
    bull_case: str = Field(description="Summary of primary bullish catalysts and technical support")
    bear_case: str = Field(description="Summary of downside risks and overhead resistance")
    debate_synthesis: str = Field(description="Reconciliation explaining the winning thesis")

class RiskAssessment(BaseModel):
    volatility_regime: Literal["LOW", "NORMAL", "ELEVATED", "EXTREME"]
    atr_14: float
    invalidation_stop_loss: float
    take_profit_targets: List[float]
    risk_reward_ratio: float

class OrderSizingParameters(BaseModel):
    target_entry_price: float
    position_size_usd: float
    base_quantity: float
    max_slippage_pct: float = Field(default=0.5, description="Max allowed slippage percentage")
    gas_threshold_usd: float = Field(default=25.0, description="Max gas fee threshold")

class CryptoRecommendation(BaseModel):
    symbol: Literal["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    timestamp: str
    action: Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
    confidence: float = Field(ge=0.0, le=1.0)
    deliberation: DeliberationDebate
    risk_assessment: RiskAssessment
    order_sizing: OrderSizingParameters

# 2. Multi-Source Ingestion Engine
class CryptoMarketDataFeed:
    def __init__(self):
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.fng_url = "https://api.alternative.me/fng/?limit=1"
        self.defillama_url = "https://api.llama.fi/v2/chains"

    def get_market_snapshot(self, symbol: str):
        # A. Fetch OHLCV (1h, 50 bars)
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        # B. Technical Indicators
        df['tr'] = df[['high', 'close']].max(axis=1) - df[['low', 'close']].min(axis=1)
        df['atr_14'] = df['tr'].rolling(14).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # C. Order Book Depth
        ob = self.exchange.fetch_order_book(symbol, limit=10)
        best_bid = ob['bids'][0][0] if ob['bids'] else None
        best_ask = ob['asks'][0][0] if ob['asks'] else None
        spread = best_ask - best_bid if (best_bid and best_ask) else 0.0

        # D. Macro Sentiment (Fear & Greed)
        fng_res = requests.get(self.fng_url).json()
        fng_score = int(fng_res['data'][0]['value'])
        fng_class = fng_res['data'][0]['value_classification']

        # E. DefiLlama Chain Fundamentals
        llama_res = requests.get(self.defillama_url).json()
        chain_name = "Ethereum" if "ETH" in symbol else ("Solana" if "SOL" in symbol else "Bitcoin")
        chain_tvl = next((c['tvl'] for c in llama_res if c['name'] == chain_name), None)

        return {
            "symbol": symbol,
            "current_price": float(df['close'].iloc[-1]),
            "atr_14": float(df['atr_14'].iloc[-1]),
            "ema_20": float(df['ema_20'].iloc[-1]),
            "ema_50": float(df['ema_50'].iloc[-1]),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "fear_and_greed_score": fng_score,
            "fear_and_greed_classification": fng_class,
            "chain_tvl_usd": chain_tvl
        }
```

---

## 5. Live Streaming Architecture into Visualization UI

To achieve responsive UI interactions without blocking the multi-agent deliberation loop, the system adopts a **dual-channel decoupled streaming model**:

```
+-----------------------------------------------------------------------------------+
|                            MARKET DATA INGESTION                                  |
|         CCXT (Binance/Coinbase)  |  DeFiLlama TVL  |  Alternative.me F&G          |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        FASTAPI BACKEND STREAMING SERVER                           |
|                                                                                   |
|   [Channel 1: Fast-Path Market Ticks]       [Channel 2: Slow-Path Deliberation]   |
|   WebSocket (/ws/market-ticks)              SSE Stream (/api/deliberation/stream) |
|   - 1-sec price updates                     - Agent State Transitions             |
|   - Live Candlestick rendering              - Bull/Bear Reasoning Tokens          |
|   - Order book depth updates                - Structured Order Recommendation     |
+-----------------------------------------------------------------------------------+
             |                                              |
             v                                              v
+-----------------------------------------------------------------------------------+
|                         TRADING VISUALIZATION UI                                  |
|                                                                                   |
|   +-----------------------------+    +----------------------------------------+   |
|   |   Live K-Line Chart Panel   |    |    AI Deliberation / Reasoning Stream  |   |
|   |   - OHLCV + Indicators      |    |    - Analyst Team Logs                 |   |
|   |   - Active Stop/TP Overlays |    |    - Bull vs. Bear Debate Arena        |   |
|   +-----------------------------+    +----------------------------------------+   |
|   +---------------------------------------------------------------------------+   |
|   |                       Order Execution & Telemetry Panel                   |   |
|   |   - Signal: BUY BTC/USDT (Confidence: 82%) | Size: $1,000.00               |   |
|   |   - Safeguards: Max Slippage 0.5% | Max Gas $25.00                        |   |
|   |   - Action Button: [Approve & Sign with MetaMask]                         |   |
|   +---------------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

### 5.1 Dual-Channel Protocols
1. **WebSocket (`/ws/market-ticks`)**:
   - Transmits sub-second price ticks and 1-minute OHLCV candles to the frontend chart engine.
   - Low latency, bidirectional connection.
2. **Server-Sent Events (SSE) (`/api/deliberation/stream`)**:
   - Emits structured event frames:
     - `stage_change`: Emits `{ "from": "Analyst_Ingestion", "to": "Bull_Bear_Debate" }`
     - `reasoning_chunk`: Emits `{ "agent": "Bull_Researcher", "token": "..." }`
     - `order_recommendation`: Emits validated `CryptoRecommendation` JSON payload upon completion.

### 5.2 Human-in-the-Loop Safeguard Integration
When an order recommendation is finalized:
1. The UI highlights the recommended trade in the Telemetry Panel.
2. The UI checks the execution mode:
   - **Frontier / Semi-Automated Mode**: The trade remains in `PENDING_APPROVAL` status until the trader clicks "Approve & Sign". Clicking initiates the MetaMask wallet connection (Requirement R2) for on-chain signing.
   - **Autopilot Mode**: The trade passes directly to the local execution validator. If maximum allocation caps, slippage limits, and gas thresholds are satisfied, the transaction is signed and broadcast automatically.

---

## 6. Implementation Action Plan & Downstream Milestones

### Milestone 1: Data Ingestion & Indicator Service
- Create `src/data_feed/crypto_feed.py` implementing CCXT Binance/Coinbase public market connectors, DeFiLlama TVL queries, and Alternative.me sentiment ingestion for BTC, ETH, and SOL.
- Implement ATR-based dynamic risk sizing calculations and exchange step-size precision formatting.

### Milestone 2: `agy --remote-agent` Deliberation Subprocess
- Create `src/agent/remote_deliberation.py` encapsulating the CLI invocation of `agy --remote-agent -p ... --output-format json`.
- Implement JSON schema validation against the `CryptoRecommendation` Pydantic model with retry fallback.

### Milestone 3: Visualization UI Deployment & Bridge
- Set up **HKUDS/Vibe-Trading** (or NOFX with FastAPI adapter) using Docker Compose.
- Expose `/ws/market-ticks` and `/api/deliberation/stream` endpoints to bridge `TradingAgents` live telemetry to the web dashboard.

### Milestone 4: Integration Verification & Paper Trading
- Execute end-to-end integration test: Market Ingestion -> `agy --remote-agent` Deliberation -> UI SSE Streaming -> MetaMask Execution Safeguard verification.
