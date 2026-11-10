# TauricResearch/TradingAgents Architecture & Agent Hierarchy Survey Report

**Survey Target**: `TauricResearch/TradingAgents` (https://github.com/TauricResearch/TradingAgents)  
**Surveyed By**: `teamwork_explorer_survey_1`  
**Milestone**: Phase 0 — Scope & Architecture Survey (Requirement R1)  
**Date**: 2026-11-06  
**Repository Version Evaluated**: v0.7.1 (commit on `main` branch, SHA `bf78b34e3533f50fdd2e62be099271a8641eefe7`)

---

## Executive Summary

The `TauricResearch/TradingAgents` repository implements an institutional-grade, multi-agent financial trading framework powered by LLMs and orchestrated with LangGraph (`langgraph>=1.2.12`). The architecture decomposes the trading pipeline into four distinct organizational layers:
1. **Analyst Team** (Parallel specialized analysts: Market, Sentiment/Social, News/Macro, Fundamentals).
2. **Researcher Team** (Dynamic Bull vs. Bear debate supervised by a Research Manager).
3. **Trader Agent** (Translates the strategic research plan and market price structure into concrete transaction proposals).
4. **Risk Management & Portfolio Manager Team** (Tripartite risk debate between Aggressive, Conservative, and Neutral analysts, adjudicated by the Portfolio Manager who issues the final 5-tier rating and sizing).

The framework includes robust mechanisms for point-in-time data integrity, crash recovery via SQLite checkpointing, cross-ticker reflection memory with automated alpha settlement against benchmark indices, and native support for cryptocurrency pairs (`BTC-USD`, `ETH-USD`, `SOL-USD`).

This report provides the exhaustive technical breakdown required for integrating TauricResearch/TradingAgents into Antigravity, aligning with the Google Antigravity SDK (`google-antigravity-sdk`), and fulfilling Requirement R1.

---

## 1. Repository Structure & Code Organization

### 1.1 Directory Tree & Module Boundaries
```
TradingAgents/
├── pyproject.toml              # Setuptools build spec, runtime & dev dependencies
├── requirements.txt            # Package install pointer ('.')
├── Dockerfile                  # Containerized deployment spec
├── docker-compose.yml          # Multi-container service definitions
├── .env.example                # Canonical environment variable configuration template
├── main.py                     # Entry point forwarding to cli.main:app
├── cli/                        # Interactive Typer/Rich terminal user interface
│   ├── main.py                 # CLI command definitions ('analyze', 'backtest', 'login', 'logout')
│   ├── run.py                  # Single analysis execution loop, message streaming, decorators
│   ├── display.py              # Rich layout panels, terminal formatting, wall-time tracking
│   ├── models.py               # Enums: AnalystType, AssetType, ResearchDepth, Language
│   ├── prefs.py                # User preferences persistence (~/.tradingagents/prefs.json)
│   ├── prompts.py              # Interactive questionary wizard & parameter prompts
│   ├── selections.py           # Unattended parameter gathering & validation
│   ├── stats_handler.py        # Token counting and latency callback handler
│   └── updates.py              # Upstream GitHub release checking
├── tradingagents/              # Core framework package
│   ├── default_config.py       # Configuration dictionary factory & env variable coercion
│   ├── backtest.py             # Multi-ticker, multi-date grid runner and scoring engine
│   ├── portfolio.py            # Caller position & cash book representation (Pydantic)
│   ├── reporting.py            # Markdown report generator & multi-file report tree writer
│   ├── report_html.py          # Standalone single-page HTML report compiler
│   ├── agents/                 # Agent node definitions and prompting logic
│   │   ├── state.py            # AgentState, InvestDebateState, RiskDebateState schemas
│   │   ├── schemas.py          # Pydantic schemas for structured output (ResearchPlan, TraderProposal, PortfolioDecision, SentimentReport)
│   │   ├── structured.py       # LangChain structured output binding & fallback engine
│   │   ├── tools.py            # LangChain @tool definitions with InjectedState
│   │   ├── context.py          # Instrument identity resolution & prompt context assemblers
│   │   ├── rating.py           # 5-tier rating normalization (Buy/Overweight/Hold/Underweight/Sell)
│   │   ├── post_screen.py      # TypeSafe Jev social post screening integration
│   │   ├── analysts/           # Specialized analyst nodes
│   │   │   ├── market_analyst.py
│   │   │   ├── sentiment_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   └── turn.py         # Multi-turn tool execution loop & max_tool_rounds wrap-up
│   │   ├── researchers/        # Bull/Bear debate nodes
│   │   │   ├── bull_researcher.py
│   │   │   └── bear_researcher.py
│   │   ├── managers/           # Manager synthesis nodes
│   │   │   ├── research_manager.py
│   │   │   └── portfolio_manager.py
│   │   ├── risk_mgmt/          # Tripartite risk debate nodes
│   │   │   ├── aggressive_debator.py
│   │   │   ├── conservative_debator.py
│   │   │   └── neutral_debator.py
│   │   └── trader/
│   │       └── trader.py       # Trader transaction proposal generation
│   ├── dataflows/              # Vendor routing and data retrieval engine
│   │   ├── router.py           # Vendor method dispatch and fallback resolution
│   │   ├── config.py           # Thread-local / ContextVar configuration scoping
│   │   ├── symbols.py          # Symbol normalization, crypto detection, path sanitization
│   │   ├── date_window.py      # Look-ahead prevention and point-in-time date slicing
│   │   ├── errors.py           # VendorUnavailableError, NoMarketDataError
│   │   ├── files.py            # Local cache file access
│   │   ├── net.py              # HTTP session handling and retry logic
│   │   └── vendors/            # Specialized external API adapters
│   │       ├── yahoo/          # Yahoo Finance (yfinance) adapter
│   │       ├── alpha_vantage/  # Alpha Vantage API adapter
│   │       ├── fred.py         # Federal Reserve Economic Data (FRED)
│   │       ├── polymarket.py   # Prediction market odds
│   │       ├── reddit.py       # Reddit public RSS search parser
│   │       ├── stocktwits.py   # StockTwits cashtag stream parser
│   │       └── sec_edgar.py    # SEC EDGAR company filings parser
│   ├── graph/                  # LangGraph execution engine
│   │   ├── trading_graph.py    # TradingAgentsGraph orchestration class
│   │   ├── setup.py            # GraphSetup: node registration and edge wiring
│   │   ├── conditional_logic.py# Conditional routing logic for debate loops
│   │   ├── analyst_execution.py# Parallel analyst execution plan
│   │   ├── checkpointer.py     # SQLite checkpointing and thread identification
│   │   └── propagation.py      # Initial state constructor & recursion limits
│   ├── llm_clients/            # Multi-provider LLM abstraction layer
│   │   ├── base_client.py      # BaseLLMClient interface & output normalization
│   │   ├── factory.py          # create_tier_client factory (quick vs. deep tiers)
│   │   ├── google_client.py    # Google Gemini client (NormalizedChatGoogleGenerativeAI)
│   │   ├── openai_client.py    # OpenAI client with ChatGPT Plus/Pro OAuth support
│   │   ├── anthropic_client.py # Anthropic Claude client
│   │   ├── azure_client.py     # Azure OpenAI client
│   │   ├── bedrock_client.py   # AWS Bedrock client
│   │   ├── model_catalog.py    # Supported model definitions and tier mapping
│   │   └── validators.py       # Provider model validation
│   └── memory/                 # Persistent memory and self-reflection engine
│       ├── log.py              # TradingMemoryLog: markdown decision storage & retrieval
│       ├── reflection.py       # Reflector: post-trade LLM self-evaluation against realized prices
│       └── settlement.py       # Outcome settlement & benchmark alpha calculation
└── tests/                      # 88 isolated test suites (unit, smoke, integration)
```

---

## 2. Complete Agent Hierarchy & Specializations

The agent hierarchy consists of 10 specialized agent roles divided into 4 tiers, plus 1 concurrent memory management step:

```
                                  [START]
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
   ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
   │ Market        │         │ Sentiment     │         │ News          │
   │ Analyst       │         │ Analyst       │         │ Analyst       │
   │ (Technicals)  │         │ (Social/News) │         │ (Macro/Events)│
   └───────┬───────┘         └───────┬───────┘         └───────┬───────┘
           │                         │                         │
           │        ┌────────────────┴───────────────┐         │
           │        ▼                                ▼         │
   ┌───────┴───────┐                         ┌───────┴───────┐ │
   │ Fundamentals  │                         │ Memory Log    │ │
   │ Analyst (SEC) │                         │ Settle/Reflect│ │
   └───────┬───────┘                         └───────┬───────┘ │
           │                                         │         │
           └──────────────────┬──────────────────────┴─────────┘
                              │ (Join Barrier)
                              ▼
                     ┌─────────────────┐
                     │ Bull Researcher │◄─────────┐
                     └────────┬────────┘          │
                              ▼                   │ (Debate Loop:
                     ┌─────────────────┐          │  2 * max_debate_rounds)
                     │ Bear Researcher ├──────────┘
                     └────────┬────────┘
                              ▼ (Consensus reached)
                     ┌─────────────────┐
                     │ Research        │
                     │ Manager         │
                     └────────┬────────┘
                              ▼
                     ┌─────────────────┐
                     │ Trader Agent    │
                     └────────┬────────┘
                              ▼
                     ┌─────────────────┐
                     │ Aggressive      │◄─────────┐
                     │ Risk Analyst    │          │
                     └────────┬────────┘          │
                              ▼                   │ (Risk Loop:
                     ┌─────────────────┐          │  3 * max_risk_rounds)
                     │ Conservative    │          │
                     │ Risk Analyst    │          │
                     └────────┬────────┘          │
                              ▼                   │
                     ┌─────────────────┐          │
                     │ Neutral         ├──────────┘
                     │ Risk Analyst    │
                     └────────┬────────┘
                              ▼ (Risk consensus reached)
                     ┌─────────────────┐
                     │ Portfolio       │
                     │ Manager         │
                     └────────┬────────┘
                              │
                            [END]
```

### 2.1 Tier 1: Analyst Teams
Each analyst executes in an isolated subgraph with a private message history (`tradingagents/graph/setup.py:53-90`). They return only their specialized text report, eliminating prompt pollution across analysts.
- **Market Analyst** (`tradingagents/agents/analysts/market_analyst.py`):
  - *Tools*: `get_stock_data`, `get_indicators`, `get_verified_market_snapshot`.
  - *Domain*: Technical analysis across 5 indicator families: Moving Averages (50 SMA, 200 SMA, 10 EMA), MACD (line, signal, histogram), Momentum (RSI), Volatility (Bollinger Bands, ATR), and Volume (VWMA).
  - *Guardrail*: Requires calling `get_verified_market_snapshot` as the ground truth before asserting price claims to prevent hallucinations.
- **Sentiment Analyst** (`tradingagents/agents/analysts/sentiment_analyst.py`):
  - *Tools*: Pre-fetches news headlines (Yahoo), StockTwits messages, and Reddit discussions across selected subreddits (past 7-day lookback).
  - *Domain*: Quantitative retail-sentiment ratio (e.g. 70/30 Bull/Bear), divergence between institutional headlines and social sentiment, narrative themes.
  - *Output*: Emits structured `SentimentReport` containing `overall_band` (Bullish, Mildly Bullish, Neutral, Mixed, Mildly Bearish, Bearish), `overall_score` (0.0 to 10.0), `confidence` (low, medium, high), and narrative.
  - *Jev Screening*: Optional post filtering via TypeSafe Jev API (`post_screen.py`).
- **News Analyst** (`tradingagents/agents/analysts/news_analyst.py`):
  - *Tools*: `get_news`, `get_global_news`, `get_macro_indicators`, `get_prediction_markets`.
  - *Domain*: Asset-specific news, global macroeconomic headlines, macroeconomic indicator series from FRED (e.g., CPI, core PCE, unemployment, Fed funds rate, 10-year Treasury, yield curve), and live prediction market probabilities from Polymarket.
- **Fundamentals Analyst** (`tradingagents/agents/analysts/fundamentals_analyst.py`):
  - *Tools*: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions`.
  - *Domain*: Company profiles, quarterly/annual financial statement analysis, SEC filings, insider trading activity.
  - *Asset Mode Filtering*: Automatically excluded when analyzing cryptocurrency assets (`detect_asset_type` / `filter_analysts_for_asset_type`), as crypto tokens do not file corporate 10-K/10-Q statements.

### 2.2 Tier 2: Researcher Teams (Bull vs. Bear Debate)
- **Bull Researcher** (`tradingagents/agents/researchers/bull_researcher.py`):
  - Ingests all analyst reports, instrument context, and debate history.
  - Formulates an aggressive growth case focusing on upside opportunities, competitive moats, positive technical/sentiment indicators, and refutes bear counterpoints.
- **Bear Researcher** (`tradingagents/agents/researchers/bear_researcher.py`):
  - Ingests all analyst reports, instrument context, and debate history.
  - Systematically exposes valuation risks, financial vulnerabilities, negative catalysts, competitive threats, and flaws in the bull thesis.
- **Research Manager** (`tradingagents/agents/managers/research_manager.py`):
  - Acts as debate facilitator.
  - Evaluates argument merits regardless of speaking order.
  - Emits structured `ResearchPlan` (`schemas.py:95-139`) with:
    - `recommendation`: 5-tier rating (`Buy`, `Overweight`, `Hold`, `Underweight`, `Sell`).
    - `rationale`: Synthesis of which debate points prevailed.
    - `strategic_actions`: Specific guidelines for execution sizing.

### 2.3 Tier 3: Trader Agent
- **Trader Agent** (`tradingagents/agents/trader/trader.py`):
  - Bridges research synthesis and live execution.
  - Ingests the `ResearchPlan`, technical market report (for price structure: current price, support/resistance, ATR volatility), and optional caller portfolio context.
  - Emits structured `TraderProposal` (`schemas.py:146-213`) with:
    - `action`: 3-tier directional transaction (`Buy`, `Hold`, `Sell`).
    - `reasoning`: Clear logic anchored in technical levels and research strategy.
    - `entry_price`: Numeric price target in quote currency (percentages and ranges explicitly forbidden).
    - `stop_loss`: Absolute numeric price level.
    - `position_sizing`: Allocation guidance (e.g., "5% of portfolio").

### 2.4 Tier 4: Risk Management & Portfolio Manager
- **Risk Management Debaters** (`tradingagents/agents/risk_mgmt/`):
  - **Aggressive Risk Analyst** (`aggressive_debator.py`): Champions high-upside, high-risk strategies; argues against over-conservative assumptions.
  - **Conservative Risk Analyst** (`conservative_debator.py`): Emphasizes capital preservation, drawdown minimization, volatility capping, and downside hedging.
  - **Neutral Risk Analyst** (`neutral_debator.py`): Advocates balanced risk-reward, diversification, and steady growth.
- **Portfolio Manager** (`tradingagents/agents/managers/portfolio_manager.py`):
  - Final decision authority.
  - Synthesizes risk debate history, research plan, trader proposal, caller portfolio context, and past decision reflections from `TradingMemoryLog`.
  - Emits structured `PortfolioDecision` (`schemas.py:221-289`) with:
    - `rating`: Final 5-tier rating (`Buy`, `Overweight`, `Hold`, `Underweight`, `Sell`).
    - `executive_summary`: Concise operational action plan (entry, sizing, horizons).
    - `investment_thesis`: Comprehensive justification citing debate evidence.
    - `price_target`: Absolute numeric target.
    - `time_horizon`: Holding period recommendation.

---

## 3. Communication, State Propagation, & Deliberation Mechanics

### 3.1 LangGraph State Architecture
The global graph state is governed by `AgentState` (`tradingagents/agents/state.py`), inheriting from LangGraph's `MessagesState`:
```python
class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company/Asset ticker under analysis"]
    asset_type: Annotated[str, "Asset type: stock or crypto"]
    instrument_context: Annotated[str, "Deterministic ticker identity resolved at start"]
    trade_date: Annotated[str, "Analysis date (YYYY-MM-DD)"]
    market_report: Annotated[str, "Report from Market Analyst"]
    sentiment_report: Annotated[str, "Report from Sentiment Analyst"]
    news_report: Annotated[str, "Report from News Analyst"]
    fundamentals_report: Annotated[str, "Report from Fundamentals Analyst"]
    investment_debate_state: Annotated[InvestDebateState, "Researcher debate state"]
    investment_plan: Annotated[str, "Synthesized plan from Research Manager"]
    trader_investment_plan: Annotated[str, "Concrete proposal from Trader"]
    risk_debate_state: Annotated[RiskDebateState, "Risk management debate state"]
    final_trade_decision: Annotated[str, "Rendered decision from Portfolio Manager"]
    final_rating: Annotated[str, "Portfolio Manager 5-tier rating or REVIEW"]
    past_context: Annotated[str, "Lessons from memory log"]
    memory_note: Annotated[str, "Settlement/read diagnostics"]
    portfolio_context: Annotated[str, "Caller holdings & cash context"]
```

Sub-states manage iterative turn counters:
- `InvestDebateState`: `bull_history`, `bear_history`, `history`, `current_response`, `count`.
- `RiskDebateState`: `aggressive_history`, `conservative_history`, `neutral_history`, `history`, `latest_speaker`, `current_aggressive_response`, `current_conservative_response`, `current_neutral_response`, `count`.

### 3.2 State Deliberation & Conditional Routing
Deliberation flow is deterministic and governed by `ConditionalLogic` (`tradingagents/graph/conditional_logic.py`):
1. **Parallel Analyst Execution & Memory Settlement**:
   - `START` broadcasts to `Market Analyst`, `Sentiment Analyst`, `News Analyst`, `Fundamentals Analyst` (if stock), and `Memory Log`.
   - Tool calling is bounded by `max_tool_rounds` (default: 20). If an analyst exhausts its tool limit, `wrap_up` forces immediate report generation (`setup.py:76-89`), preventing infinite recursion.
   - All branches join at `Bull Researcher`.
2. **Researcher Debate Routing**:
   - `should_continue_debate`:
     - Checks `count >= 2 * max_debate_rounds` (default `max_debate_rounds=1`, meaning 1 turn Bull, 1 turn Bear).
     - If count reached: routes to `Research Manager`.
     - Else: toggles between `Bull Researcher` and `Bear Researcher`.
   - Uses `DEBATE_PATH_MAP` to ensure all edge outcomes are mapped, preventing mid-run routing crashes.
3. **Trader Transition**:
   - `Research Manager` transitions directly to `Trader`.
   - `Trader` transitions directly to `Aggressive Analyst`.
4. **Risk Debate Routing**:
   - `should_continue_risk_analysis`:
     - Checks `count >= 3 * max_risk_discuss_rounds` (default `max_risk_discuss_rounds=1`, meaning 1 turn each for Aggressive, Conservative, Neutral).
     - If count reached: routes to `Portfolio Manager`.
     - Else: cycles `Aggressive` → `Conservative` → `Neutral` → `Aggressive`.
   - Uses `RISK_ANALYSIS_PATH_MAP`.
5. **Portfolio Manager Adjudication**:
   - `Portfolio Manager` produces `final_trade_decision` and `final_rating`, transitioning to `END`.

### 3.3 SQLite Checkpoint & Crash Resilience
In `tradingagents/graph/checkpointer.py` and `tradingagents/graph/trading_graph.py`:
- Enabled via `checkpoint_enabled=True` (or `--checkpoint` CLI flag).
- Creates an isolated SQLite database per ticker at `<data_cache_dir>/checkpoints/<ticker>.db`.
- Thread ID incorporates a deterministic SHA-256 fingerprint of the run signature (`analysts`, `debate_rounds`, `risk_rounds`, `asset_type`, `portfolio_fingerprint`, and config settings).
- Resuming a run (`checkpoint_input`) invokes LangGraph with `None` rather than re-passing initial state, preventing duplicated state messages.
- Clears checkpoint on successful completion to avoid stale state.

---

## 4. Antigravity & Google Antigravity SDK (`google-antigravity-sdk`) Integration

### 4.1 Native Google / Gemini Model Integration
TauricResearch/TradingAgents already natively supports Google Gemini through `langchain-google-genai>=4.4.0` in `tradingagents/llm_clients/google_client.py`:
- `GoogleClient` configures `NormalizedChatGoogleGenerativeAI` to handle multi-block output from Gemini 3 models.
- Maps `GOOGLE_API_KEY` (or `GEMINI_API_KEY`).
- Configures thinking levels via `TRADINGAGENTS_GOOGLE_THINKING_LEVEL` (`high`, `low`, `minimal`).
- Supported models in `model_catalog.py`: `gemini-3.8-flash` (quick tier default), `gemini-3.1-pro-preview` (deep tier default), `gemini-3.5-flash`, `gemini-3.1-flash-lite`.

### 4.2 Mapping to Antigravity SDK Agent Hierarchy
The Google Antigravity SDK (`google.antigravity`, version 0.1.22 installed in the environment) defines:
- `Agent` and `LocalAgentConfig`: Host configuration, model selection (`gemini-3.8-flash`), connection strategy (`LocalConnectionStrategy`), and capabilities.
- Multi-tier Subagent Hierarchies (`examples/getting_started/subagents.md`):
  - Root Agent: `TradingOrchestrator` or `PortfolioManager` with `CapabilitiesConfig(enable_subagents=True, max_subagent_depth=3)`.
  - Mid-tier Subagents:
    - `research_team` (`SubagentConfig(name="research_team", allowed_subagents=["bull_researcher", "bear_researcher", "research_manager"])`).
    - `analyst_team` (`SubagentConfig(name="analyst_team", allowed_subagents=["market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst"])`).
    - `risk_team` (`SubagentConfig(name="risk_team", allowed_subagents=["aggressive_debator", "conservative_debator", "neutral_debator"])`).
    - `trader` (`SubagentConfig(name="trader")`).
  - Leaf Subagents: Leaf tools only, `allowed_subagents=[]`.
- `google.antigravity.workflows`:
  - Provides workflow primitives: `@workflows.define`, `workflows.parallel`, `workflows.pipeline`, `workflows.phase`.
  - Allows constructing the TradingAgents pipeline directly as an executable Antigravity Workflow.

### 4.3 Integration with `agy --remote-agent` (Requirement R4)
The requirement specifies running the multi-agent deliberation pipeline via `agy --remote-agent` across major cryptocurrencies (`BTC`, `ETH`, `SOL`).
- **CLI Architecture**: The Antigravity language server (`C:\Users\AmirM\AppData\Local\Programs\antigravity\resources\bin\language_server.exe`) manages the agent execution runtime.
- **Workflow / Command Shim**: An `agy.bat` or CLI executable can be surfaced on the system PATH to wrap `cli.main:app` or invoke the Antigravity workflow runner:
  ```bash
  agy --remote-agent --ticker BTC-USD --asset-type crypto --save --show
  ```
- **Remote Agent Pipeline Execution**:
  - Automatically loads cryptocurrency market feeds, social feeds (Reddit `r/Bitcoin`, `r/CryptoCurrency`, StockTwits cashtags), and macro feeds.
  - Automatically suppresses fundamentals analysis.
  - Produces structured output decisions (`Buy`, `Hold`, `Sell`) with entry price, stop-loss, and sizing parameters.

---

## 5. Data Ingestion, Simulation, & Paper Trading

### 5.1 Ingestion Sources & Vendors
Data routing is managed by `tradingagents/dataflows/router.py`:
| Category | Primary Vendor | Fallback Vendor | Description & Authentication |
|---|---|---|---|
| **Core Stock / OHLCV** | `yfinance` | `alpha_vantage` | End-of-day and intraday OHLCV bars. No key required for yfinance; `ALPHA_VANTAGE_API_KEY` for AV. |
| **Technical Indicators** | `yfinance` + `stockstats` | `alpha_vantage` | 50/200 SMA, 10 EMA, MACD, RSI, Bollinger Bands, ATR, VWMA computed locally via `stockstats`. |
| **Market Snapshot** | `snapshot.py` (yfinance) | N/A | Deterministic snapshot verifying latest price, moving averages, and volatility. |
| **Fundamentals Data** | `sec_edgar` (US stocks) | `yfinance`, `alpha_vantage` | As-filed 10-K/10-Q balance sheets, income statements, cash flows. SEC requires `SEC_EDGAR_USER_AGENT`. |
| **News Feed** | `yfinance` | `alpha_vantage` | Company headlines & global macro search queries (`global_news_queries`). |
| **Macro Indicators** | `fred.py` (St. Louis Fed) | N/A | 30+ economic series (CPI, PCE, Fed funds rate, 10Y yield). Requires `FRED_API_KEY`. |
| **Prediction Markets** | `polymarket.py` | N/A | Polymarket Gamma API for event contracts (Fed rate cut, macro odds). No key required. |
| **Social Sentiment** | `stocktwits.py` & `reddit.py` | N/A | StockTwits cashtag stream; Reddit Atom/RSS search (`r/wallstreetbets`, `r/stocks`, `r/investing`). |

### 5.2 Cryptocurrency Data Handling
In `tradingagents/dataflows/symbols.py` and `tests/test_crypto_asset_mode.py`:
- **Symbol Normalization**: Recognizes crypto bases (`BTC`, `ETH`, `SOL`, `XRP`, `ADA`, `DOGE`, etc.) and formats them into Yahoo Finance syntax `BTC-USD`, `ETH-USD`, `SOL-USD`. Strips `USDT`/`USDC` suffixes and replaces them with `-USD`.
- **Crypto Asset Detection**: Automatically flags `AssetType.CRYPTO` if the symbol matches `<BASE>-USD` or a known crypto base.
- **Analyst Pruning**: For crypto assets, `filter_analysts_for_asset_type` automatically strips `fundamentals`, running only `market`, `social`, and `news`.
- **Targeted Subreddits**:
  - `BTC` → `r/Bitcoin`, `r/CryptoCurrency`, `r/CryptoMarkets`
  - `ETH` → `r/ethereum`, `r/CryptoCurrency`, `r/CryptoMarkets`
  - `SOL` → `r/solana`, `r/CryptoCurrency`, `r/CryptoMarkets`

### 5.3 Point-in-Time Data Guard & Look-Ahead Prevention
All dated tools (`get_stock_data`, `get_indicators`, `get_news`, etc.) accept `InjectedState("trade_date")` and pass dates through `as_of` / `as_of_window` (`date_window.py`).
- Data published after the analysis `trade_date` is strictly filtered out.
- Future trade dates beyond the current date are rejected.
- Social media and RSS feeds are window-bounded where available.

### 5.4 Simulation, Paper Trading, & Backtesting Engine
In `tradingagents/backtest.py`, `tradingagents/portfolio.py`, and `tradingagents/memory/`:
- **Standing Portfolio Book**: `PortfolioContext` (`portfolio.py`) represents free cash, currency, and positions (`Position: ticker, quantity, average_price`).
- **Memory Log & Reflection**:
  - Decisions are recorded in `trading_memory.md` (`TradingMemoryLog`).
  - Next time the instrument is analyzed, `_memory_step` checks for pending decisions whose holding window (`holding_period_days`, default 5 days) has elapsed.
  - `Reflector` calls the LLM to analyze the realized price outcome and benchmark return (SPY or regional index), computing **realized alpha** and recording actionable lessons.
  - Past lessons are injected into the Portfolio Manager's context for subsequent runs.
- **Backtesting Sweep Engine**:
  - `run_backtest(tickers, dates, config)` iterates across a Cartesian product of tickers and dates.
  - Evaluates decision hit rates (Buy/Overweight expected positive alpha; Sell/Underweight expected negative alpha; Hold neutral).
  - Summarizes results via `BacktestSummary`: hit rate percentage, mean alpha vs. benchmark, resolved vs. pending counts.

---

## 6. Runtime Dependencies, Environment Requirements, & Configuration

### 6.1 Python & Environment Requirements
- **Python Version**: Python `>=3.11` (Host has Python 3.11.9 at `C:\Program Files\Python311\python.exe`).
- **Core Dependencies** (`pyproject.toml`):
  - `langchain-core>=1.6.5`
  - `langchain-google-genai>=4.4.0`
  - `langchain-openai>=1.6.6`
  - `langchain-anthropic>=1.7.4`
  - `langgraph>=1.2.12`
  - `langgraph-checkpoint-sqlite>=3.1.1`
  - `pandas>=3.0.6`
  - `pydantic>=2.10`
  - `yfinance>=1.7.0`
  - `stockstats>=0.6.5`
  - `typer>=0.21.0`
  - `rich>=14.0.0`
  - `cryptography>=42.0`
  - `python-dotenv>=1.0.0`
  - `requests>=2.32.4`
  - `markdown-it-py>=4.0`
  - `pytz>=2025.2`
  - `questionary>=2.1.0`
- **Optional Dependencies**:
  - `langchain-aws>=1.7.9` (for AWS Bedrock)
  - `pytest>=8.0`, `ruff>=0.16` (development & testing)

### 6.2 Key Configuration Parameters & Environment Variables
Configured via `.env` or system environment variables:
- **LLM Selection**:
  - `TRADINGAGENTS_LLM_PROVIDER`: `google` (or `openai`, `anthropic`, `deepseek`, etc.)
  - `TRADINGAGENTS_QUICK_THINK_LLM`: `gemini-3.8-flash` (serves analysts, researchers, trader, risk analysts)
  - `TRADINGAGENTS_DEEP_THINK_LLM`: `gemini-3.1-pro-preview` (serves Research Manager & Portfolio Manager)
  - `GOOGLE_API_KEY`: Google Gemini API key
  - `TRADINGAGENTS_GOOGLE_THINKING_LEVEL`: `high`
- **Deliberation Knobs**:
  - `TRADINGAGENTS_MAX_DEBATE_ROUNDS`: `1` (Bull/Bear debate rounds)
  - `TRADINGAGENTS_MAX_RISK_ROUNDS`: `1` (Risk management discussion rounds)
  - `TRADINGAGENTS_MAX_TOOL_ROUNDS`: `20` (Tool calling ceiling per analyst)
  - `TRADINGAGENTS_CHECKPOINT_ENABLED`: `true` (Enable SQLite state checkpointing)
- **Data & Paths**:
  - `TRADINGAGENTS_RESULTS_DIR`: Output reports directory (default: `~/.tradingagents/logs`)
  - `TRADINGAGENTS_CACHE_DIR`: SQLite checkpoints & cached data (default: `~/.tradingagents/cache`)
  - `TRADINGAGENTS_MEMORY_LOG_PATH`: Decision log file (default: `~/.tradingagents/memory/trading_memory.md`)
  - `FRED_API_KEY`: St. Louis Fed FRED API key (free registration)
  - `SEC_EDGAR_USER_AGENT`: Contact string for SEC EDGAR filings (e.g. `TradingAgent user@example.com`)
  - `TRADINGAGENTS_BENCHMARK_TICKER`: Regional benchmark index override (e.g. `SPY`, `^GSPC`)

---

## 7. Integration Blueprint for Requirement R1

To complete Requirement R1 in the Antigravity workspace:
1. **Clone & Install**:
   - Clone repository directly into workspace `Agentic trading/TradingAgents` or install as editable package (`pip install -e ./TradingAgents`).
2. **Configure `.env`**:
   - Set `TRADINGAGENTS_LLM_PROVIDER=google`, `TRADINGAGENTS_QUICK_THINK_LLM=gemini-3.8-flash`, `TRADINGAGENTS_DEEP_THINK_LLM=gemini-3.1-pro-preview`.
   - Configure `GOOGLE_API_KEY`, `SEC_EDGAR_USER_AGENT`, and `FRED_API_KEY`.
3. **End-to-End Offline Test Verification**:
   - Run the mocked end-to-end graph test suite (`tests/test_graph_end_to_end.py`) using `pytest -m unit` to verify all 10 agent roles, router methods, and state persistence without external network dependencies.
4. **Antigravity / `agy` Remote Agent Binding**:
   - Establish an Antigravity wrapper script exposing `agy --remote-agent` that executes `TradingAgentsGraph.propagate()` for `BTC-USD`, `ETH-USD`, and `SOL-USD` with `asset_type="crypto"`.
5. **Execution Bridge Handshake**:
   - The structured output `TraderProposal` and `PortfolioDecision` emit explicit parameters (`final_rating`, `action`, `entry_price`, `stop_loss`, `position_sizing`). These fields form the clean interface contract to feed into Requirement R2 (MetaMask wallet execution safeguards) and Requirement R3 (Trading Visualization Interface).

---

## Conclusion
TauricResearch/TradingAgents provides a complete, mature, institutional multi-agent architecture with native LangGraph orchestration, Pydantic structured schemas, point-in-time data safety, and built-in crypto asset awareness. It integrates directly with Google Gemini and the Google Antigravity SDK, providing a solid foundation for the Agentic Trading project.
