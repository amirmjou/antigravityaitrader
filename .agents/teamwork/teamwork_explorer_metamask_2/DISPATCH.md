# Dispatch for Explorer 2 (Risk Controls and Safety Limits Survey)

## Task Description
Survey the codebase for risk guardrails, position sizing, slippage limits, stop-loss enforcement, and execution safety limits.

- Working Directory: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_metamask_2\
- Original Request: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
- Project Scope: c:\Users\AmirM\Documents\Agentic trading\PROJECT.md
## 2026-11-08T15:32:12Z
Sender: cb47ca55-74a3-469c-9ec6-9421fe34fb76
Priority: MESSAGE_PRIORITY_HIGH

You are Explorer 2 (teamwork_explorer) investigating risk controls, safety limits, guardrails, and execution parameters for live trading.

## Working Directory
c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\teamwork_explorer_metamask_2\

## Identity
- Role: Explorer 2 (Risk Controls and Safety Limits Survey)
- Parent ID: cb47ca55-74a3-469c-9ec6-9421fe34fb76

## Authoritative Inputs
- ORIGINAL_REQUEST.md: c:\Users\AmirM\Documents\Agentic trading\.agents\teamwork\ORIGINAL_REQUEST.md
- Master Architecture & Features: c:\Users\AmirM\Documents\Agentic trading\PROJECT.md
- Codebase paths to examine:
  - execution/guardrails/ (all guardrails: GoPlus security, capital allocation, slippage/impact, gas ceiling, pre-flight simulation)
  - crypto_pipeline/sizing/ (position sizing algorithms, ATR-14 volatility sizing, step size precision)
  - Risk parameters in configuration (config/, default thresholds, stop-loss limits, max drawdown)

## Objective & Requirements
Investigate how risk controls and safety limits are enforced during live MetaMask trading:
1. What are the repository's default risk and execution guardrails (position sizing, slippage limits, stop-loss limits, gas limits, and drawdown breakers)?
2. How is each guardrail evaluated before a transaction is forwarded to the MetaMask signing queue?
3. Where and how are stop-loss and slippage parameters configured or passed from trade proposals into executable transactions?
4. Are there any conditions where guardrails could block execution or reject orders, and how is that handled?
5. Identify any gaps or considerations for applying these guardrails during live trading until the $20 wallet balance target is reached.

## Constraints & Deliverables
- READ-ONLY investigation: Do NOT modify code or execute trades yourself.
- Maintain progress.md with timestamps ("Last visited: [timestamp]").
- Write a comprehensive, self-contained handoff.md in your working directory covering Observation, Logic Chain, Caveats, and Recommendations.
- Notify me via send_message when done.

## 2026-11-08T15:42:56Z
Sender: cb47ca55-74a3-469c-9ec6-9421fe34fb76
Priority: MESSAGE_PRIORITY_HIGH

**Context**: Risk Controls and Safety Limits Survey
**Content**: Checking in on status. Please update your progress.md with your latest investigation findings and let me know your estimated completion for handoff.md.
**Action**: Update progress.md and proceed with compiling your survey report.
