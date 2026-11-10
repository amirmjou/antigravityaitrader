# Arbitrum Pre-Flight Validation Checklist

Before signing and broadcasting any transaction on Arbitrum One:

1. **Chain ID Verification**: Ensure `chainId == 42161`.
2. **Native Gas Reserve Floor**: Ensure `eth_balance >= 0.00005 ETH` after deducting estimated gas fees.
3. **Simulation via `eth_call`**: Run `contract.functions.exactInputSingle(...).call({'from': wallet_address})` before sending the real signed transaction. If simulation reverts, abort and log exact revert reason.
4. **Token Decimals Precision**:
   - `WETH`: 18 decimals (`1e18`)
   - `USDC`: 6 decimals (`1e6`)
   - Never mix integer scales!
5. **Nonce Synchronization**: Fetch nonce with `"pending"` tag (`w3.eth.get_transaction_count(address, 'pending')`) to prevent duplicate nonce collisions during back-to-back operations.
