# Arbitrum L2 Sharp Edges & Pitfalls

## 1. Out-of-Gas on Simple WETH Wrapping
* **Symptom**: Transaction receipt shows `status: 0`, `gasUsed: 44785` (or near 45,000).
* **Cause**: On L1 Ethereum, `deposit()` takes ~28,000 gas. On Arbitrum One, ArbOS calculates an additional L1 calldata fee that pushes effective gas demand above 45,000.
* **Resolution**: Always set `gas = 120000` on WETH wrapping transactions on Arbitrum.

## 2. Uniswap v3 `STF` (SafeTransferFrom) Revert
* **Symptom**: `exactInputSingle` reverts immediately with error `STF`.
* **Cause**: The contract does not have sufficient token allowance, or the wallet's token balance is less than `amountIn` (often happens if a previous wrap failed silently).
* **Resolution**: Pre-flight verify that `token.balanceOf(address) >= amount_in` and `token.allowance(address, router) >= amount_in`.

## 3. Gas Reserve Starvation (Brick Trap)
* **Symptom**: Wallet converts 100% of native ETH into WETH or USDC, leaving 0 ETH for gas. The wallet cannot execute any further transactions to convert back.
* **Resolution**: Maintain a strict circuit-breaker: Never let native ETH drop below `0.00005 ETH`.
