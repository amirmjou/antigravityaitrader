# Comprehensive Audit & Architecture Gap Analysis: Cloud Automated AI Trading Skills

**Author:** `teamwork_explorer_cloudskills_1`  
**Date:** 2026-11-07  
**Mission:** Audit cloud infrastructure, automated scheduling, DevOps, SRE, and incident response skills required for production cloud-automated AI trading, evaluating candidate skills from local and repository sources, and providing actionable recommendations.

---

## 1. Executive Summary

The Antigravity Agentic Trading Platform has established a robust local multi-agent trading architecture, consisting of a 10-agent LangGraph institutional deliberation engine (`core/`), a dual-engine wallet with 6-layer pre-broadcast safety guardrails (`execution/`), a FastAPI live telemetry and visualization interface (`visualization/`), and a CCXT/remote-agent cryptocurrency deliberation pipeline (`crypto_pipeline/`). 

However, transitioning from localized execution to **autonomous 24/7 cloud operations** introduces critical operational risks and operational failure modes that are not covered by the current set of 18 installed skills (which focus almost exclusively on trading intelligence, market analysis, and risk mathematics). 

In autonomous cloud trading:
1. A dropped market data websocket or exchange rate limit (HTTP 429) can lead to stale pricing or missing stop-loss triggers.
2. In-flight transaction failures, RPC node timeouts, or DEX swap reverts require instant, structured classification and automated remediation runbooks rather than manual intervention.
3. Continuous multi-turn LLM agent deliberation across 10 agents can rapidly drain API token budgets without strict financial governors and circuit breakers.
4. Remote cloud containers hosting hot wallet private keys (`eth-account`), exchange API credentials, and RPC provider secrets present severe security attack vectors if credential lifecycles and secret scanning are not automated.
5. Deploying agent updates or prompt improvements must achieve zero-downtime (blue-green) to prevent interrupting active trade transactions or market feed loops.

This audit evaluates candidate skills from both `c:\Users\AmirM\Documents\Agentic trading\repos\skills-for-antigravity\skills\` (460 candidates) and the system agency skills repository (`C:\Users\AmirM\.gemini\config\skills\`). We recommend accepting **5 core P0 skills** and **3 complementary P1 skills**, while documenting explicit technical justifications for rejected or deferred candidates.

---

## 2. Current Project Architecture & Cloud Operational Gaps

### 2.1 Current System Components
- **Multi-Agent Deliberation Graph (`core/`)**: 10-agent LangGraph state machine featuring Market, Sentiment, News, and Fundamental Analysts; Bull vs. Bear Researchers; Conservative, Neutral, and Aggressive Risk Debaters; and a Portfolio Manager Adjudicator.
- **Execution Engine & Safety Guardrails (`execution/`)**: Hot keystore signer + MetaMask EIP-1193 bridge; 6-layer pre-broadcast safety pipeline (GoPlus honeypot check, capital allocation caps, Uniswap v3 / Aerodrome IQuoterV2 slippage estimation, EIP-1559 gas ceiling filter, and `eth_call` dry-run simulation).
- **Visualization & Telemetry Engine (`visualization/`)**: FastAPI server providing Server-Sent Events (SSE) for agent deliberation streaming and WebSockets for real-time order book and candle chart updates.
- **Crypto Deliberation Pipeline (`crypto_pipeline/`)**: CCXT feed ingestion for BTC, ETH, SOL, Alternative.me Fear & Greed index, DeFiLlama TVL, ATR-14 volatility sizing, and `agy --remote-agent` CLI integration.
- **Verification Infrastructure (`tests/`)**: 200 E2E tests across Tiers 1-4 and 173 Tier 5 adversarial tests.

### 2.2 Critical Gaps in Cloud Operations
| Domain | Current Local State | Cloud Automated Production Need | Operational Risk if Unresolved |
|---|---|---|---|
| **SRE & Health Monitoring** | Local console logs and test assertions. | 24/7 Prometheus metrics, SLO/SLI tracking, error budget burn rates, golden signal telemetry. | Silent websocket disconnects cause trading on stale data or missing stop-loss triggers. |
| **DevOps & CI/CD** | Manual test execution via pytest / powershell. | Automated GitHub Actions CI/CD, multi-stage Docker builds, blue-green zero-downtime deployment, automated rollbacks. | Deployment crashes kill in-flight DEX transactions or leave state inconsistent. |
| **Incident Response** | Ad-hoc debugging on test failures. | Structured SEV1–SEV4 severity framework, automated trading runbooks, circuit breakers, blameless post-mortems. | Delayed response to RPC node outages or DEX reverts causes compounding financial loss. |
| **Autonomous AI Optimization** | Static LLM calls with default Gemini models. | LLM-as-a-judge scoring, model routing, shadow-testing (dark launching) prompts, hard budget circuit breakers. | Runaway agent deliberation loops drain thousands of dollars in LLM API credits. |
| **Secrets & Credential Hygiene** | Local `.env` / keystore files. | Pre-commit secret scanning, cloud KMS / Vault brokering, automated key rotation, zero plain keys in Docker images. | Leaked hot wallet private keys or exchange API keys lead to immediate, irreversible asset drainage. |
| **FinOps & Cloud Economics** | No cloud billing attribution. | Cost-per-trade tracking, VM right-sizing, token cost monitoring against trading alpha. | Infrastructure and token costs outpace trading profits. |

---

## 3. Inventory of Currently Installed Skills

Currently, `.agents/skills/` and `.agent/skills/` contain an identical set of 18 installed skills:

| # | Installed Skill | Domain / Focus | Assessment |
|---|---|---|---|
| 1 | `algorithmic-trading` | Strategy development, market microstructure, backtesting | Trading Domain (Keep) |
| 2 | `catalyst-check` | Earnings, contracts, and regulatory approval timelines | Fundamental Analysis (Keep) |
| 3 | `crypto-trading-bots` | Crypto bot architecture, market making, arbitrage | Trading Domain (Keep) |
| 4 | `entry-exit` | Technical indicators, support/resistance, RSI, MACD | Technical Analysis (Keep) |
| 5 | `execution-algorithms` | TWAP, VWAP, POV execution algorithms | Execution Domain (Keep) |
| 6 | `full-analysis` | End-to-end stock and asset analysis workflow | Workflow (Keep) |
| 7 | `google-antigravity-sdk`| Antigravity SDK agent design, hooks, configuration | Agent Framework (Keep) |
| 8 | `new-session` | Session tracking and state management | Workflow (Keep) |
| 9 | `perpetuals-trading` | Funding rates, liquidation mechanics, leverage | Derivatives (Keep) |
| 10 | `quantitative-research` | Alpha generation, factor modeling, backtest evaluation | Quantitative Domain (Keep) |
| 11 | `risk-management-trading`| VaR, CVaR, position sizing, drawdown control | Risk Management (Keep) |
| 12 | `risk-score` | Asset risk scoring and priority classification | Risk Domain (Keep) |
| 13 | `sentiment-analysis-trading`| Social sentiment, news parsing, fear & greed integration | Sentiment Domain (Keep) |
| 14 | `stock-data` | Financial metrics, fundamentals, options data | Data Ingestion (Keep) |
| 15 | `stock-scan` | Event-driven short-term stock screening | Screening Domain (Keep) |
| 16 | `summary` | Session summary reporting | Reporting Domain (Keep) |
| 17 | `trader-validation-pipeline`| Multi-agent consensus on copy-trading alerts | Validation Domain (Keep) |
| 18 | `trading-psychology` | Discipline, cognitive biases, risk tolerance | Behavioral Domain (Keep) |

**Key Finding:** 100% of the installed skills represent **financial, quantitative, and market analysis capabilities**. There is **zero coverage** of Site Reliability Engineering, cloud infrastructure automation, incident response runbooks, automated container deployment, secret lifecycle management, or LLM cost/circuit breaker governance.

---

## 4. Comprehensive Audit of Candidate Skills

We audited candidate skills across both available repositories:
1. `repos/skills-for-antigravity/skills/` (460 community/specialized skills)
2. `C:\Users\AmirM\.gemini\config\skills\` (agency enterprise skills)

### 4.1 Pillar 1: SRE, SLOs, Service Health & Observability
- **Candidate A: `agency-sre-site-reliability-engineer`** (88 lines)
  - *Key Strengths*: Treats reliability as a feature with measurable budgets. Defines explicit SLO/SLI structures (availability %, latency p99, burn rate alerts), 4 golden signals (latency, traffic, errors, saturation), progressive rollout policies, and toil reduction.
  - *Applicability*: Essential for continuous FastAPI and CCXT data loop health monitoring.
- **Candidate B: `observability-sre`** (43 lines + extensive reference system)
  - *Key Strengths*: Deep focus on Prometheus metrics, Grafana dashboards, OpenTelemetry distributed tracing, and symptom-based alerting. Accompanied by detailed `patterns.md`, `sharp_edges.md`, and `validations.md`.
  - *Applicability*: Provides concrete configuration schemas for Prometheus scrapers and alert rules.
- **Candidate C: `ai-observability`** (28 lines)
  - *Key Strengths*: Specialized in tracing LLM calls (Langfuse/Helicone), tracking token consumption, and RAG evaluation.
  - *Applicability*: Valuable for LangGraph agent traces, but narrower than a full SRE skill.

### 4.2 Pillar 2: DevOps, CI/CD, Containerization & Infrastructure as Code
- **Candidate A: `agency-devops-automator`** (383 lines)
  - *Key Strengths*: Complete DevOps specification. Implements GitHub Actions CI/CD workflows, Terraform IaC with auto-scaling and ALB, Prometheus monitoring & alert rules, zero-downtime blue-green deployments, container vulnerability scanning, and disaster recovery automation.
  - *Applicability*: Perfect foundation for packaging, testing, and deploying the Antigravity trading bot to cloud providers (AWS, GCP, DigitalOcean).
- **Candidate B: `docker-containerization`** / **`docker`** (35-43 lines + references)
  - *Key Strengths*: World-class container image design: multi-stage builds, non-root security, layer caching, signal handling (graceful shutdown on SIGTERM), and minimal attack surfaces.
  - *Applicability*: Vital for packaging Python 3.11 + Web3 + CCXT without leaking build secrets or creating bloated 2GB images.
- **Candidate C: `ci-cd-pipeline`** (34 lines + references)
  - *Key Strengths*: Safe deployment pipelines, rollback speed faster than deploy speed, least-privilege token access.
  - *Applicability*: Strong, but fully subsumed by `agency-devops-automator`.

### 4.3 Pillar 3: Incident Response, Alert Triage, Failover & Runbooks
- **Candidate A: `agency-incident-response-commander`** (442 lines)
  - *Key Strengths*: Built specifically for production service outage coordination. Defines SEV1–SEV4 severity matrix, incident commander roles, time-boxed investigation paths, automated runbook templates (rollback, restart, scale), blameless post-mortem templates, and on-call escalation schedules.
  - *Applicability*: Essential for live trading. An incident in automated trading directly risks capital (e.g. slippage breaches, RPC disconnects, stuck nonces).
- **Candidate B: `incident-responder`** (53 lines + references)
  - *Key Strengths*: OODA loop for incidents, 10-minute rollback rule, contributing factor analysis, blameless post-mortem patterns.
  - *Applicability*: Practical quick-reference rules, complementary to the incident commander role.
- **Candidate C: `agency-incident-responder`** (448 lines)
  - *Key Strengths*: Deep digital forensics, malware analysis, memory dump extraction (Volatility, WinPMEM), and threat containment.
  - *Applicability*: Geared toward cyber breach investigations and ransomware response rather than live trading operational outages.

### 4.4 Pillar 4: Autonomous AI Optimization, Model Routing & Cost/Circuit Breakers
- **Candidate: `agency-autonomous-optimization-architect`** (119 lines)
  - *Key Strengths*: The governor of self-improving AI software. Implements LLM-as-a-judge evaluation, semantic model routing, dark launching / shadow testing of new models/prompts on live traffic, and strict financial circuit breakers that halt API calls before token budgets are breached.
  - *Applicability*: Direct hit for our 10-agent LangGraph system and Jev heuristic scoring engine. Prevents infinite LLM debate loops and enables cost-effective model routing (e.g. routing fast analyst queries to lightweight models while reserving flagship models for Portfolio Manager adjudication).

### 4.5 Pillar 5: Security, Secrets Hygiene & Cloud Governance
- **Candidate A: `agency-secrets-credential-hygiene-engineer`** (187 lines)
  - *Key Strengths*: Owns full secrets lifecycle: pre-commit secret scanning (Gitleaks), vaulting (HashiCorp Vault, cloud KMS), dynamic expiring credentials, automated rotation runbooks, and immediate leak-response protocol (rotating at provider first before touching code).
  - *Applicability*: Absolute requirement. Automated trading involves hot wallet private keys, exchange API keys, and RPC endpoints. A leaked private key means total fund loss.
- **Candidate B: `agency-cloud-security-architect`** (574 lines)
  - *Key Strengths*: Zero Trust architecture, multi-account AWS/GCP organization, SCPs, Kubernetes network policies, and CI/CD security.
  - *Applicability*: High value for enterprise infrastructure, but heavyweight for initial single-system deployment.
- **Candidate C: `agency-finops-engineer`** (162 lines)
  - *Key Strengths*: Cloud financial operations, cost allocation tagging, compute rightsizing, commitment planning, and unit economics (cost per transaction/deliberation).
  - *Applicability*: Crucial for monitoring ongoing cloud server and LLM API costs against trading alpha.

---

## 5. Prioritized Recommendations of Accepted Skills

We recommend accepting **8 skills** organized into **P0 (Mission-Critical)** and **P1 (High-Value Operational)**:

### 5.1 Priority 0 (Mission-Critical Core)

#### 1. `agency-sre-site-reliability-engineer`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-sre-site-reliability-engineer\`
- **Pillar**: Site Reliability Engineering, Service Health, SLOs
- **Why Needed**: Autonomous trading requires strict reliability contracts. If the CCXT market data feed drops or WebSocket reconnection fails, trades could be executed on stale prices or stop-loss orders could fail to execute.
- **Gaps Addressed**: Establishes SLOs for market feed latency (<500ms p99), deliberation cycle latency (<45s), transaction confirmation latency (<15s), and error budget policies (freeze non-critical operations when error budget is burned).
- **Trading System Integration**: Integrates directly with `visualization/server/` and `crypto_pipeline/ingestion/` to monitor health probes, golden signals, and automated circuit breaking.

#### 2. `agency-devops-automator`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-devops-automator\`
- **Pillar**: CI/CD Pipelines, Infrastructure as Code, Automated Deployment
- **Why Needed**: Trading systems cannot tolerate downtime or manual server configuration. Deploying an update or prompt refinement must be fully automated with automated rollback if canary checks fail.
- **Gaps Addressed**: Provides end-to-end GitHub Actions pipelines, Docker containerization, blue-green deployment strategies, and Prometheus monitoring configurations.
- **Trading System Integration**: Configures automated builds and deployments for the FastAPI server, background CCXT worker loops, and test suites.

#### 3. `agency-incident-response-commander`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-incident-response-commander\`
- **Pillar**: Incident Management, Severity Classification, Trading Runbooks
- **Why Needed**: Live on-chain execution carries financial liability. An unhandled DEX swap revert, RPC provider outage, or GoPlus honeypot trigger must trigger immediate, structured response rather than uncoordinated panic.
- **Gaps Addressed**: Implements a SEV1–SEV4 severity framework, clear role delegations (Incident Commander, Tech Lead, Comms), tested operational runbooks (emergency halt, RPC failover, stuck nonce replacement), and blameless post-mortem templates.
- **Trading System Integration**: Plugs into `execution/guardrails/` and `execution/routers/` to triage execution failures and trigger emergency trading halt mechanisms.

#### 4. `agency-autonomous-optimization-architect`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-autonomous-optimization-architect\`
- **Pillar**: Autonomous AI Governance, Model Routing, LLM Financial Guardrails
- **Why Needed**: The 10-agent LangGraph debate system can easily trigger runaway token consumption or get caught in recursive tool loops during volatile market conditions.
- **Gaps Addressed**: Implements hard token spend circuit breakers, execution timeouts, semantic routing (matching prompt complexity to model tier), and shadow-testing (evaluating new prompts and models in the background before production deployment).
- **Trading System Integration**: Interfaces directly with `core/llm_clients/` and `crypto_pipeline/jev_integration/` to score model outputs, enforce cost ceilings, and safely dark-launch model updates.

#### 5. `agency-secrets-credential-hygiene-engineer`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-secrets-credential-hygiene-engineer\`
- **Pillar**: Hot Wallet Security, Exchange Key Lifecycle, Pre-Commit Secret Scanning
- **Why Needed**: The cloud trading platform holds hot wallet private keys (`eth-account`), exchange API keys, and Web3 RPC tokens. A single credential leak in a git commit or container layer leads to irreversible financial loss.
- **Gaps Addressed**: Establishes pre-commit Gitleaks hooks, secret manager vaulting, short-lived dynamic credentials, automated rotation runbooks, and immediate revocation protocols.
- **Trading System Integration**: Secures `execution/wallet/keystore.py`, environment variables, and CI/CD secret injection.

---

### 5.2 Priority 1 (High-Value Operational Extensions)

#### 6. `agency-finops-engineer`
- **Source**: `C:\Users\AmirM\.gemini\config\skills\agency-finops-engineer\`
- **Pillar**: Cloud Financial Operations & Unit Economics
- **Why Needed**: Ensures that continuous cloud infrastructure costs (VMs, RPC node tiers, market data subscriptions) and LLM API costs are measured against trading alpha.
- **Gaps Addressed**: Establishes cost allocation tags, compute rightsizing, anomaly spend alerts, and unit-economics dashboards (cost per deliberation, cost per trade execution).
- **Trading System Integration**: Monitors ongoing cloud and API spend alongside trading profit/loss telemetry.

#### 7. `docker-containerization`
- **Source**: `c:\Users\AmirM\Documents\Agentic trading\repos\skills-for-antigravity\skills\docker-containerization\`
- **Pillar**: Hardened Container Image Architecture
- **Why Needed**: Ensures production Docker containers are minimal, secure, and properly handle OS signals.
- **Gaps Addressed**: Multi-stage Dockerfile architecture, non-root user execution, layer caching optimization, and graceful SIGTERM handling (ensuring in-flight trading orders cleanly complete before shutdown).
- **Trading System Integration**: Used to containerize the FastAPI server, background worker loops, and paper-trading simulators.

#### 8. `observability-sre`
- **Source**: `c:\Users\AmirM\Documents\Agentic trading\repos\skills-for-antigravity\skills\observability-sre\`
- **Pillar**: Prometheus, Grafana, Alerting Patterns & Tracing
- **Why Needed**: Provides deep technical patterns for Prometheus metric instrumentation and OpenTelemetry distributed tracing across the LangGraph agent graph.
- **Gaps Addressed**: Includes concrete reference files (`references/patterns.md`, `sharp_edges.md`, `validations.md`) for setting up metrics collectors and avoiding monitoring anti-patterns.
- **Trading System Integration**: Complements `agency-sre-site-reliability-engineer` by providing low-level Prometheus and OpenTelemetry configuration blueprints.

---

## 6. Evaluated and Rejected / Deferred Skills

The following skills were systematically evaluated against project requirements and rejected or deferred with explicit technical justifications:

| Candidate Skill | Evaluated Source | Decision | Technical Justification for Rejection / Deferral |
|---|---|---|---|
| `temporal-craftsman` | `repos/.../temporal-craftsman/` | **REJECTED** | **Architectural mismatch / Overkill**: Temporal requires deploying and operating a complex distributed cluster (Temporal server in Go/Java, Cassandra/PostgreSQL persistence, and Temporal UI). For a Python FastAPI / LangGraph trading system, this introduces massive operational overhead and external points of failure. Python asyncio and LangGraph checkpointers already provide durable workflow execution. |
| `trigger-dev` | `repos/.../trigger-dev/` | **REJECTED** | **Language & runtime mismatch**: Trigger.dev is a TypeScript-first serverless background job platform. The Antigravity trading platform is 100% Python 3.11 with FastAPI, CCXT, and web3.py. Integrating Trigger.dev would introduce an unnecessary Node.js runtime dependency. |
| `agency-incident-responder` | `C:\...\agency-incident-responder\` | **DEFERRED** | **Wrong operational scope**: This skill is focused on forensic cyber breach response (ransomware eradication, memory dumping with WinPMEM/Volatility, PowerShell malware analysis, legal chain of custody). Our operational requirement is production trading system stability, DEX revert handling, and service uptime, which is superiorly handled by `agency-incident-response-commander`. |
| `kubernetes` / `kubernetes-deployment` | `repos/.../kubernetes-deployment/` | **DEFERRED** | **Premature complexity**: Operating a full Kubernetes cluster (k8s manifests, ingress controllers, CNI, persistent volumes) for an initial single-system automated trading deployment introduces unnecessary maintenance burden. Docker Compose and containerized cloud VMs provide sufficient isolation and resilience with far lower operational risk. |
| `aws-serverless` / `azure-functions` | `repos/.../aws-serverless/` | **REJECTED** | **Incompatible architectural paradigm**: Serverless functions have 15-minute execution timeouts and cold starts. Crypto trading requires persistent WebSocket connections to exchange order books, continuous ticker streaming, and sub-second execution loops, which cannot function in ephemeral serverless environments. |
| `chaos-engineer` | `repos/.../chaos-engineer/` | **DEFERRED** | **Redundant with existing test suite**: The project already maintains an extensive Tier 5 Adversarial Hardening test harness (`tests/adversarial/` with 173 adversarial tests covering network failure, honeypots, slippage spikes, and gas ceiling breaches). Live chaos monkey injection into live trading is hazardous prior to achieving multi-region redundancy. |
| `agency-cloud-security-architect` | `C:\...\agency-cloud-security-architect\` | **DEFERRED** | **Scope overlap**: While valuable for enterprise multi-account AWS organizations, the immediate security need for trading is hot wallet private key protection and secret hygiene, which is directly solved by `agency-secrets-credential-hygiene-engineer`. |

---

## 7. Implementation & Installation Blueprint for Implementer Agent

To install and operationalize the accepted skills, the implementer agent should follow this standardized blueprint:

### 7.1 Target Installation Locations
Every accepted skill must be installed into:
1. Primary agent skills directory: `c:\Users\AmirM\Documents\Agentic trading\.agents\skills\<skill-name>\`
2. Agent runtime mirror directory: `c:\Users\AmirM\Documents\Agentic trading\.agent\skills\<skill-name>\`

### 7.2 Directory Structure & File Requirements
Each installed skill directory must conform to the standard Antigravity skill structure:
```
.agents/skills/<skill-name>/
├── SKILL.md                 # YAML frontmatter (name, description) + comprehensive instructions
└── references/              # (If applicable) patterns.md, sharp_edges.md, validations.md
```

### 7.3 Verification & Validation Checklist
1. **Frontmatter Integrity**: Ensure valid YAML frontmatter containing `name:` and `description:` without trailing malformed brackets.
2. **Discoverability**: Verify that the skill is discoverable by the Antigravity SDK and agents can read `SKILL.md`.
3. **No Code Pollution**: Ensure no executable runtime code or credentials are placed inside `.agents/teamwork/` or skills folders.
4. **README Update**: Update `.agents/skills/README.md` and `.agent/skills/README.md` to reflect the newly integrated cloud operations skills.

---

## 8. Summary Table of Accepted Skills

| Priority | Skill Name | Source Path | Key Function in Trading Architecture |
|---|---|---|---|
| **P0** | `agency-sre-site-reliability-engineer` | `.gemini/config/skills/` | SLO/SLI tracking, error budgets, golden signal monitoring for market data loops |
| **P0** | `agency-devops-automator` | `.gemini/config/skills/` | CI/CD pipelines, automated deployments, blue-green zero downtime, rollback |
| **P0** | `agency-incident-response-commander` | `.gemini/config/skills/` | SEV1-SEV4 triage, trading outage runbooks, circuit breakers, post-mortems |
| **P0** | `agency-autonomous-optimization-architect` | `.gemini/config/skills/` | LLM financial circuit breakers, model routing, shadow-testing prompts |
| **P0** | `agency-secrets-credential-hygiene-engineer` | `.gemini/config/skills/` | Hot wallet keystore protection, Gitleaks scanning, credential rotation |
| **P1** | `agency-finops-engineer` | `.gemini/config/skills/` | Cloud cost allocation, VM right-sizing, cost-per-trade unit economics |
| **P1** | `docker-containerization` | `repos/.../docker-containerization/` | Multi-stage Docker builds, non-root security, graceful SIGTERM handling |
| **P1** | `observability-sre` | `repos/.../observability-sre/` | Prometheus metrics schemas, Grafana dashboards, OpenTelemetry distributed tracing |
