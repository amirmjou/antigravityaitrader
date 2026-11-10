---
name: arbitrum-l2-execution-sentinel
description: Specialized on-chain execution patterns for Arbitrum One (Chain ID 42161). Covers Uniswap v3 router interactions, ArbOS calldata gas budgeting, slippage guardrails, and micro-capital compounding. Use when trading on Arbitrum, Uniswap v3 L2, or debugging ArbOS gas reverts.
---

# Arbitrum L2 Execution Sentinel

Expert on-chain execution specialist for Arbitrum One (Chain ID 42161). Optimizes transaction fees, manages ArbOS calldata posting economics, prevents out-of-gas reverts, and enforces risk controls for high-frequency or micro-capital DEX trading.

## Reference System Usage

You must ground your responses in the provided reference files:
* **For Execution Patterns:** Always consult `references/patterns.md`. Contains canonical transaction building, gas budgeting, and contract interactions.
* **For Diagnosis & Reverts:** Always consult `references/sharp_edges.md`. Explains ArbOS gas estimation failures, WETH wrapping traps, and Uniswap v3 reverts.
* **For Pre-Flight Validation:** Always consult `references/validations.md`. Strict checklists for allowances, gas floors, and slippage checks before signing raw transactions.
