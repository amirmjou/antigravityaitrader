# Arbitrum Execution Patterns

## 1. ArbOS Gas Budgeting
Arbitrum One charges two fee components:
1. **L2 Execution Fee**: Extremely low (~0.01 - 0.05 Gwei).
2. **L1 Calldata Posting Fee**: Dynamic fee charged by ArbOS to post transaction batches to Ethereum L1.

### Gas Limits:
- **ETH ➔ WETH Wrap (`deposit`)**: 120,000 gas units (standard 45,000 L1 limit will revert out-of-gas).
- **ERC20 Router Approval**: 75,000 gas units.
- **Uniswap v3 `exactInputSingle` Swap**: 300,000 gas units.
- **Gas Price Multiplier**: `gas_price * 1.25` buffer ensures inclusion in the immediate L2 sequencer batch.

## 2. Canonical Arbitrum One Addresses (Chain ID 42161)
- **WETH9**: `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1`
- **Native USDC**: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` (6 decimals)
- **Uniswap v3 SwapRouter02**: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
- **Default Uniswap v3 Pool Fee**: `500` (0.05% fee tier for high-liquidity stable/major pairs).

## 3. Resilient RPC Failover
Always cycle through multiple independent public RPC endpoints:
```python
ARBITRUM_RPC_URLS = [
    "https://arb1.arbitrum.io/rpc",
    "https://arbitrum-one.publicnode.com",
    "https://1rpc.io/arb",
    "https://arbitrum.llamarpc.com",
]
```
