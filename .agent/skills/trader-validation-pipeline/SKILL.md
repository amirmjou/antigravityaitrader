---
name: trader-validation-pipeline
description: Intercepts copy-trading alerts to verify liquidity, market regime fit, and run a multi-agent consensus validation before routing executions.
---
# Protocol
- When a trader-alert is triggered, capture the exact entry asset, price, and timestamp.
- Route the asset to a multi-agent verification loop: Agent 1 checks market regime (trending vs mean-reverting), Agent 2 checks order book depth to ensure slippage stays under 0.15%.
- Reject the trade instantly if the asset is in a macro overbought zone or if order book liquidity is thin.
- Execute only if a unanimous consensus is achieved, setting a strict dynamic trailing ATR stop-loss.
