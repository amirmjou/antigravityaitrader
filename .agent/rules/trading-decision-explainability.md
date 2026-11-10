# Rule: Trading Decision Explainability & Accountability

All autonomous trading agents, daemons, and execution modules in this project must adhere to the following mandatory invariants:

## 1. No Black-Box Executions
Every automated trading decision (whether a swap, wrap, liquidity position, or cancel) must generate and record an explicit, structured decision record before and after execution.

## 2. Mandatory Decision Fields
The record must contain:
1. **`regime`**: High-level market classification (`BULLISH_EXPANSION`, `BEARISH_PULLBACK`, or `CONSOLIDATION_RANGE`).
2. **`conviction_pct`**: Quantified confidence score ranging from `0.0%` to `100.0%` derived from multi-indicator agreement (e.g. MA spread + RSI alignment).
3. **`rationale`**: A clear, plain-language explanation of why the action was taken (e.g. "Fast MA ($3,135.20) crossed above Slow MA ($3,128.40) with RSI=58.4").
4. **`next_trigger`**: The precise on-chain or price threshold that will trigger the next action (e.g. "Bearish cross below $3,128.40 or RSI < 42 triggers exit to USDC").

## 3. Persistent Trade Journaling
- All trades must be saved to `data/trade_journal.json`.
- Completed round-trip trades must record entry value, exit value, net PnL (accounting for all L2 gas fees), and a win/loss boolean flag.

## 4. User Notification Transparency
Outbound alerts (such as Telegram messages) must stream the `rationale` and `conviction_pct` directly alongside transaction hashes and Arbiscan explorer links so the user always understands why a trade was made.
