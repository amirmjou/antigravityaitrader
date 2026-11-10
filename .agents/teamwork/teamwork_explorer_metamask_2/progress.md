# Progress — Explorer 2 (Risk Controls and Safety Limits Survey)

- **Status**: Deep Investigation Underway (Codebase Survey Complete, Synthesizing Handoff)
- **Last visited**: 2026-11-08T15:43:30Z
- **Estimated Completion**: ~10-15 minutes (Final handoff.md generation and verification)

## Latest Investigation Discoveries
1. **5-Layer Pre-Broadcast Safety Pipeline (`execution/guardrails/pipeline.py`)**:
   - Layer 1 (Contract Security): GoPlus integration checks self-swap, zero amounts, honeypot flags, buy/sell taxes > 1%, cannot_sell_all, and blacklists.
   - Layer 2 (Capital Allocation): Max spend cap $250 default, asset concentration cap 20% (relaxed to 98% in single-rotation micro-accounts like `evm_ten_trade_runner.py`), and 8.0% daily drawdown circuit breaker.
   - Layer 3 (Dynamic Slippage): Slippage capped at `max_slippage_bps` (50-100 bps default, 15 bps in copy-trading/micro-runner), Uniswap v3 `IQuoterV2` off-chain quoting with price impact <= 2.0%, transaction deadline between 1s and 300s.
   - Layer 4 (Gas & Congestion): Base fee <= `gas_ceiling_gwei` (120 gwei default, 5.0 gwei for L2), simulated gas 145,000 units, gas-to-trade cost ratio <= 1.5%.
   - Layer 5 (Pre-Flight Simulation): `eth_call` dry-run against the router address; intercepts EVM reverts and parses error strings.
2. **Evaluation & Signing Flow (`DualEngineWalletRouter` & `EIP1193BridgeServer`)**:
   - `PreBroadcastGuardrailPipeline.evaluate()` returns `GuardrailVerdict`. If `approved == False`, execution is hard-blocked and logged.
   - When approved, `DualEngineWalletRouter.execute_swap(signer_mode="eip1193_metamask")` stages the transaction into `EIP1193BridgeServer.stage_transaction_sync()` with a unique `request_id`, broadcasting `TRADE_STAGED` via WebSocket and exposing it to MetaMask.
3. **Stop-Loss and Slippage Propagation**:
   - Trader proposals define `stop_loss` as an absolute price in quote currency, validated by `core/agents/schemas.py` and `core/agents/jev_adapter.py`.
   - On-chain EVM DEX swaps (`exactInputSingle`) lack native stop orders; stop-loss is enforced as an off-chain trailing ATR threshold (e.g. 1.6% in `evm_ten_trade_runner.py`), triggering an exit swap when breached.
   - Slippage is passed as `slippage_bps` into `SwapTransactionRequest` and converted to `amountOutMinimum` in Uniswap v3 structs.
4. **Micro-Capital ($2.00 climbing to $20.00) Considerations**:
   - Layer 4 gas-to-trade ratio (<=1.5%) strictly forbids trading on Ethereum Mainnet L1 (where a single swap costs $2-$5+, which is 100-250% of a $2 trade).
   - Must execute strictly on L2 (Arbitrum One or Base), where fees are $0.004-$0.010 (~0.2-0.5% of trade).
   - Asset concentration limit (default 20%) would block single full-wallet trades on small balances unless adjusted (e.g. 98% as configured in `evm_ten_trade_runner.py`).
   - Native gas buffer (~$0.16 in ETH) must be reserved so the wallet does not exhaust gas.
