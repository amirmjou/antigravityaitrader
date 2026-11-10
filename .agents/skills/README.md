# Antigravity Agentic Trading Skills Catalog

This directory contains the operational skills library for the Antigravity Agentic Trading Platform. Each skill provides autonomous agents with domain-specific methodologies, schemas, and operational runbooks for cloud automated AI trading.

The catalog contains **30 active skills** categorized across five operational domains:
1. [Trading & Alpha](#1-trading--alpha) (12 skills)
2. [Execution & Safety](#2-execution--safety) (5 skills)
3. [Cloud SRE & DevOps](#3-cloud-sre--devops) (5 skills)
4. [Security & FinOps](#4-security--finops) (4 skills)
5. [API & Telemetry](#5-api--telemetry) (4 skills)

---

## Skill Architecture & Directory Convention

Each skill directory conforms to the Antigravity skill specification:
- `SKILL.md`: Root manifest containing standard YAML frontmatter (`name`, `description`) and operational instructions.
- `references/` (optional): Extended specifications, architectural patterns, failure modes, and validation checklists.
- `scripts/` (optional): Deterministic utility scripts for automated validation and execution.

Skills are co-located in `.agents/skills/` and mirrored in `.agent/skills/` to support both Antigravity subagents and standard agent tool discovery.

---

## Domain Categorization & Catalog Index

### 1. Trading & Alpha
Skills focused on market intelligence, quantitative research, catalyst monitoring, technical analysis, and multi-agent deliberation.

| Skill | Purpose & Capabilities |
|---|---|
| [`algorithmic-trading`](./algorithmic-trading/SKILL.md) | Quantitative strategy development, backtesting frameworks, statistical modeling, and microstructure analysis. |
| [`catalyst-check`](./catalyst-check/SKILL.md) | Event-driven catalyst tracking (earnings announcements, regulatory rulings, protocol upgrades, token unlocks). |
| [`crypto-trading-bots`](./crypto-trading-bots/SKILL.md) | Decentralized exchange (DEX) bot strategies, MEV protection, cross-pool arbitrage, and token sniper mitigation. |
| [`entry-exit`](./entry-exit/SKILL.md) | Technical entry/exit level formulation using support/resistance, RSI, MACD, and price targets. |
| [`full-analysis`](./full-analysis/SKILL.md) | Comprehensive asset analysis orchestrating fundamental, technical, sentiment, and catalyst dataflows. |
| [`new-session`](./new-session/SKILL.md) | Multi-turn trading session lifecycle tracking, context continuity, and state persistence. |
| [`perpetuals-trading`](./perpetuals-trading/SKILL.md) | Decentralized perpetual futures (GMX, dYdX, Hyperliquid), funding rate arbitrage, liquidation protection, and leverage mechanics. |
| [`quantitative-research`](./quantitative-research/SKILL.md) | Systematic alpha generation, factor modeling, mean-reversion, statistical arbitrage, and walk-forward analysis. |
| [`sentiment-analysis-trading`](./sentiment-analysis-trading/SKILL.md) | Alternative data parsing, Fear & Greed indexing, news sentiment, social media momentum, and on-chain whale tracking. |
| [`stock-data`](./stock-data/SKILL.md) | Asset data aggregation across market cap, financial statements, institutional holdings, and options flow. |
| [`stock-scan`](./stock-scan/SKILL.md) | Automated screening for high-momentum, breakout, and event-driven trading candidates. |
| [`summary`](./summary/SKILL.md) | Deliberation synthesis, trade thesis consolidation, and executive reporting for portfolio managers. |

---

### 2. Execution & Safety
Skills governing capital preservation, position sizing, pre-broadcast guardrails, and psychological discipline.

| Skill | Purpose & Capabilities |
|---|---|
| [`execution-algorithms`](./execution-algorithms/SKILL.md) | Smart order routing (TWAP, VWAP, iceberg orders), market impact minimization, and slippage mitigation. |
| [`risk-management-trading`](./risk-management-trading/SKILL.md) | Position sizing algorithms (Kelly Criterion, fixed-fractional), volatility targeting, max drawdown breakers, and stop-loss logic. |
| [`risk-score`](./risk-score/SKILL.md) | Multi-factor risk scoring and automated tier classification (Conservative, Moderate, Speculative). |
| [`trader-validation-pipeline`](./trader-validation-pipeline/SKILL.md) | Copy-trading alert interception, liquidity and spread verification, market regime fit checks, and multi-agent consensus validation. |
| [`trading-psychology`](./trading-psychology/SKILL.md) | Cognitive bias mitigation (FOMO, revenge trading, loss aversion), disciplined rule adherence, and trade journaling. |

---

### 3. Cloud SRE & DevOps
Skills managing cloud infrastructure reliability, 24/7 uptime, automated deployment pipelines, and incident response.

| Skill | Purpose & Capabilities |
|---|---|
| [`agency-sre-site-reliability-engineer`](./agency-sre-site-reliability-engineer/SKILL.md) | Production SRE practices, SLO/SLI definition, error budget tracking, toil reduction, and disaster recovery. |
| [`agency-devops-automator`](./agency-devops-automator/SKILL.md) | Blue-green zero-downtime deployments, CI/CD automation, infrastructure as code, and container lifecycle orchestration. |
| [`agency-incident-response-commander`](./agency-incident-response-commander/SKILL.md) | Severity-classified incident response (SEV1-SEV4), emergency trading halt protocols, and post-mortem facilitation. |
| [`docker-containerization`](./docker-containerization/SKILL.md) | Hardened multi-stage Docker builds, minimal distroless/non-root execution, layer caching, and SIGTERM graceful shutdown. |
| [`google-antigravity-sdk`](./google-antigravity-sdk/SKILL.md) | Antigravity multi-agent orchestration, agent configuration, lifecycle hooks, and tool routing patterns. |

---

### 4. Security & FinOps
Skills enforcing defense-in-depth, private key hygiene, zero-trust cloud posture, and compute/LLM cost governors.

| Skill | Purpose & Capabilities |
|---|---|
| [`agency-secrets-credential-hygiene-engineer`](./agency-secrets-credential-hygiene-engineer/SKILL.md) | Hot wallet private key vaulting, pre-commit secret leak prevention (Gitleaks), automated credential rotation, and leak incident response. |
| [`agency-cloud-security-architect`](./agency-cloud-security-architect/SKILL.md) | Zero-trust VPC network isolation, IMDSv2 SSRF mitigation for cloud trading VMs, IAM least-privilege, and defense-in-depth security. |
| [`agency-finops-engineer`](./agency-finops-engineer/SKILL.md) | Cloud compute spend governance, VM rightsizing, reservation planning, and unit-economics tracking (cost per trade/deliberation). |
| [`agency-autonomous-optimization-architect`](./agency-autonomous-optimization-architect/SKILL.md) | Runtime LLM financial circuit breakers, model routing, shadow-testing prompts, and token spend governance against runaway API costs. |

---

### 5. API & Telemetry
Skills ensuring RPC node health, low-latency execution profiling, streaming telemetry, and distributed observability.

| Skill | Purpose & Capabilities |
|---|---|
| [`agency-api-tester`](./agency-api-tester/SKILL.md) | Contract testing and health verification for EVM RPC nodes (Arbitrum, Base), CCXT exchange feeds, and GoPlus contract security APIs. |
| [`agency-performance-benchmarker`](./agency-performance-benchmarker/SKILL.md) | Tick-to-trade latency measurement, p95/p99 latency profiling, and mempool broadcast timing optimization. |
| [`agency-realtime-collaboration-engineer`](./agency-realtime-collaboration-engineer/SKILL.md) | High-throughput WebSocket and SSE streaming resilience, bounded queue backpressure, and reconnect safety with exponential backoff. |
| [`observability-sre`](./observability-sre/SKILL.md) | Prometheus trading metric schemas, Grafana dashboards, OpenTelemetry distributed tracing, and alerting strategies. |

---

## Verification & Integrity Assurance

To verify catalog completeness, schema validity, and frontmatter integrity across the repository, run the automated verification suite:

```powershell
# Verify all 30 skills in both .agents/skills and .agent/skills
$dirs = @('.agents/skills', '.agent/skills')
foreach ($base in $dirs) {
    Get-ChildItem $base -Directory | ForEach-Object {
        $skillPath = Join-Path $_.FullName 'SKILL.md'
        $hasManifest = Test-Path $skillPath
        $size = if ($hasManifest) { (Get-Item $skillPath).Length } else { 0 }
        [PSCustomObject]@{
            Catalog     = $base
            SkillName   = $_.Name
            HasManifest = $hasManifest
            Bytes       = $size
        }
    } | Format-Table -AutoSize
}
```
