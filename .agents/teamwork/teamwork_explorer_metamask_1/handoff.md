# Handoff Report: EIP-1193 MetaMask Bridge & Live DEX Execution Pipeline Survey

**Author**: Explorer 1 (teamwork_explorer_metamask_1)  
**Parent ID**: cb47ca55-74a3-469c-9ec6-9421fe34fb76  
**Timestamp**: 2026-11-08T15:45:00Z  
**Integrity Mode**: Read-Only Survey

---

## 1. Observation

Direct observations from examining the codebase, configuration files, frontend scripts, and execution routers:

### 1.1 MetaMask Wallet Connection Flow
- **Browser Provider Detection (`visualization/web/static/js/app.js:422-432`)**:
  ```javascript
  function initMetaMask() {
      var walletBtn = document.getElementById('btn-connect-wallet');
      if (!walletBtn) return;
      if (typeof window.ethereum !== 'undefined') {
          walletBtn.textContent = 'Connect MetaMask';
          walletBtn.disabled = false;
      } else {
          walletBtn.textContent = 'MetaMask Bridge Ready';
      }
  }
  ```
- **Connection Handshake (`visualization/web/static/js/app.js:437-465`)**:
  When `#btn-connect-wallet` is clicked, if `window.ethereum` is present:
  ```javascript
  Promise.all([
      window.ethereum.request({ method: 'eth_requestAccounts' }),
      window.ethereum.request({ method: 'eth_chainId' })
  ])
  .then(function(results) {
      var accounts = results[0] || [];
      var chainId = results[1] || '0xa4b1';
      if (accounts.length) {
          connectedWalletAddress = accounts[0];
          walletBtn.textContent = connectedWalletAddress.substring(0, 6) + '...' + connectedWalletAddress.substring(38);
          return fetch('/rpc', {
              method: 'POST',
              headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
              body: JSON.stringify({
                  jsonrpc: '2.0',
                  id: Date.now(),
                  method: 'wallet_syncAccount',
                  params: [connectedWalletAddress, chainId]
              })
          });
      }
  })
  ```
- **Backend Bridge Synchronization (`visualization/server/app.py:210-226`)**:
  ```python
  elif method == "wallet_syncAccount":
      params = rpc_req.params or []
      if params and isinstance(params[0], str):
          addr = params[0]
          app.state.bridge_server.set_connected_account(addr)
          if len(params) > 1 and params[1]:
              try:
                  cid = int(str(params[1]), 16) if str(params[1]).startswith("0x") else int(params[1])
                  app.state.bridge_server.chain_id = cid
              except ValueError:
                  pass
          app.state.telemetry_hub.publish_event(
              "agent_thought",
              "Execution Trader",
              f"MetaMask Wallet Connected: {addr} (Chain ID: {app.state.bridge_server.chain_id}) — Live On-Chain Execution Armed.",
          )
      return {"jsonrpc": "2.0", "id": rpc_req.id, "result": app.state.bridge_server.connected_accounts}
  ```
- **Bridge Server Storage (`execution/wallet/eip1193_bridge.py:121-124`)**:
  ```python
  def set_connected_account(self, address: str):
      if address not in self.connected_accounts:
          self.connected_accounts.insert(0, address)
  ```

---

### 1.2 Trade Transaction Construction, Queuing, and Broadcast

- **AI Deliberation & Proposal Generation (`run_live_metamask_terminal.py:173-189`)**:
  ```python
  action = "BUY" if (rsi_res.rsi_14 < 68.0 and macd_res.histogram >= -15.0) else "SELL"
  stop_px = round(live_px * (0.968 if action == "BUY" else 1.032), 2)
  btc_qty = round(40.0 / max(live_px, 1.0), 6)
  proposal_snap = {
      "action": action,
      "symbol": "BTC/USDT",
      "entry_price": live_px,
      "stop_loss": stop_px,
      "position_sizing": f"{btc_qty} BTC ($40.00)",
      "wallet": active_wallet,
  }
  hub.publish_event(
      "proposal_generated",
      "Execution Trader",
      f"PROPOSAL READY: {action} {btc_qty} BTC ($40.00) @ ${live_px:,.2f} | Stop: ${stop_px:,.2f} | Ready for MetaMask Sign ({active_wallet[:10]}...)",
      snapshot=proposal_snap,
  )
  ```
- **DEX Parameter Construction (`execution/routers/dex_router.py:95-139`)**:
  `build_exact_input_single_params()` builds the Uniswap v3 `ExactInputSingleParams`:
  `(tokenIn, tokenOut, fee, recipient, deadline, amountIn, amountOutMinimum, sqrtPriceLimitX96)`.
- **Pre-Broadcast Safety Guardrails (`execution/guardrails/pipeline.py:86-279`)**:
  Enforces a 5-layer pipeline:
  - Layer 1: GoPlus honeypot, mintable, transfer blacklist, buy/sell tax <= 1%
  - Layer 2: Capital allocation ($250 spend cap, <=20% asset concentration, <=8% daily drawdown)
  - Layer 3: Uniswap v3 IQuoterV2 off-chain pricing, <=100 bps slippage, <=2.0% price impact, <=300s deadline
  - Layer 4: Gas ceiling (base fee <=120 gwei, gas cost ratio <=1.5% of trade value)
  - Layer 5: `eth_call` dry-run simulation on RPC node.
- **Frontend Staging & MetaMask Prompt (`visualization/web/static/js/app.js:520-562`)**:
  ```javascript
  // 1. Stage transaction on bridge server
  fetch('/send-transaction', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(txPayload)
  })
  .then(function(res) { return res.json(); })
  .then(function(stagedData) {
      var requestId = stagedData.request_id;
      if (typeof window.ethereum !== 'undefined') {
          return window.ethereum.request({ method: 'eth_requestAccounts' })
              .then(function(accounts) {
                  var fromAccount = (accounts && accounts.length > 0) ? accounts[0] : undefined;
                  var ethTxParams = {
                      from: fromAccount,
                      to: txPayload.to,
                      value: '0x0',
                      data: '0x'  // <-- IMPORTANT OBSERVATION: Hardcoded empty calldata
                  };
                  return window.ethereum.request({
                      method: 'eth_sendTransaction',
                      params: [ethTxParams]
                  });
              })
              .then(function(realTxHash) {
                  return { request_id: requestId, tx_hash: realTxHash };
              });
      } else {
          // Fallback to local /rpc bridge mock
          return fetch('/rpc', { ... });
      }
  })
  ```
- **Confirmation & WebSocket Telemetry (`visualization/web/static/js/app.js:565-581` & `execution/wallet/eip1193_bridge.py:145-164`)**:
  When MetaMask finishes broadcasting, `window.ethereum.request` resolves with the transaction hash `realTxHash`.
  Frontend sends POST `/confirm-transaction` with `{"request_id": requestId, "tx_hash": realTxHash, "success": true}`.
  Backend records confirmation, removes item from `pending_transactions`, sets asyncio event, and broadcasts `TX_CONFIRMED` via WebSocket.

---

### 1.3 Configured Networks and Trading Pairs

#### Networks Configured:
1. **Arbitrum One (Chain ID: 42161)** (`execution/routers/dex_router.py:31-40`, `simulation/paper_trader/evm_ten_trade_runner.py:214-224`, `crypto_pipeline/airdrop_scanner.py:37-45`):
   - Canonical Uniswap v3 SwapRouter02: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
   - Uniswap v3 QuoterV2: `0x61fFE014bA136170505655d03170F09287640F16`
   - Wrapped Native (WETH): `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1`
   - RPC endpoints: `https://arb1.arbitrum.io/rpc`, `https://arbitrum-one-rpc.publicnode.com`
2. **Base (Chain ID: 8453)** (`execution/routers/dex_router.py:41-49`, `simulation/paper_trader/evm_ten_trade_runner.py:225-235`, `crypto_pipeline/airdrop_scanner.py:46-54`):
   - Canonical Uniswap v3 SwapRouter02: `0x2626664c2603336E57B271c5C0b26F421741e481`
   - Uniswap v3 QuoterV2: `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
   - Aerodrome Router: `0xcF77a3Ba9A5CA399B7c97c74856154938591A088`
   - Wrapped Native (WETH): `0x4200000000000000000000000000000000000006`
   - RPC endpoints: `https://mainnet.base.org`, `https://base-rpc.publicnode.com`
3. **Ethereum Mainnet (Chain ID: 1)** (`execution/routers/dex_router.py:50-59`):
   - Uniswap v3 SwapRouter02: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
   - QuoterV2: `0x61fFE014bA136170505655d03170F09287640F16`
   - Wrapped Native (WETH): `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2`
   - RPC endpoints: `https://ethereum-rpc.publicnode.com`, `https://eth.llamarpc.com`
4. **Other Supported EVM Networks (Scanner / Airdrop tools)**:
   - Optimism (10), Linea (59144), Scroll (534352), ZKsync Era (324), Sepolia Testnet (11155111).

#### Trading Pairs and Token Contracts Configured:
- **On Arbitrum One (42161)**:
  - `WETH / USDC`: WETH (`0x82aF49447D8a07e3bd95BD0d56f35241523fBab1`) & USDC (`0xaf88d065e77c8cC2239327C5EDb3A432268e5831`)
  - `WETH / WBTC`: WETH & WBTC (`0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f`)
  - `WETH / ARB`: WETH & ARB (`0x912CE59144191C1204E64559FE8253a0e49E6548`)
  - `WETH / GMX`: WETH & GMX (`0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a`)
  - `WETH / PENDLE`: WETH & PENDLE (`0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8`)
- **On Base (8453)**:
  - `WETH / USDC`: WETH (`0x4200000000000000000000000000000000000006`) & USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
  - `WETH / AERO`: WETH & AERO (`0x940181a94A35A4569E4529A3CDfB74e38FD98631`)
  - `WETH / cbBTC`: WETH & cbBTC (`0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf`)
- **Spot Market Price Feeds**:
  - `BTC-USD` / `BTC/USDT`, `ETH-USD` / `ETH/USDT`, `SOL-USD` / `SOL/USDT` (Coinbase public REST ticker + CCXT).

---

### 1.4 Runtime Environment & Bridge Process Requirements
To run live trades through MetaMask, the following components must be actively executing:
1. **Host Terminal & Bridge Server (`run_live_metamask_terminal.py:192-212`)**:
   - Runs FastAPI + Uvicorn server bound to `http://127.0.0.1:8899`.
   - Environmental variables:
     - `TRADINGAGENTS_SECURITY_MODE=production` (or `development`)
     - `TRADING_API_KEY`: token (default: `ag_live_metamask_2026_token`)
     - Required query parameter in browser: `?token=ag_live_metamask_2026_token`
   - Background tasks: `live_market_and_ai_trading_loop(app)` polls spot prices, calculates technical indicators (RSI, ADX, MACD, EMA), and streams SSE thoughts (`/events/reasoning`) and WebSockets (`/ws/telemetry`).
2. **Browser with MetaMask Extension**:
   - The user must open `http://localhost:8899/?token=ag_live_metamask_2026_token` in an Ethereum-enabled browser (Chrome, Brave, Firefox with MetaMask extension unlocked).
   - The user clicks "Connect MetaMask" to establish session parity with the bridge.
   - The active chain in MetaMask must match the target trading network (Arbitrum One 42161 or Base 8453).
   - When a proposal is generated, clicking "Confirm On-Chain Swap" opens the modal, staging the trade on `/send-transaction` and launching the MetaMask confirmation popup.

---

### 1.5 Identified Gaps & Missing Configurations for Live vs Simulation Mode

1. **Empty Calldata `data: '0x'` in `app.js` (`visualization/web/static/js/app.js:536`)**:
   - `ethTxParams` sets `data: '0x'` directly. When MetaMask broadcasts `to: 0x68b3...Fc45` (Uniswap v3 SwapRouter02) with `data: '0x'` and `value: '0x0'`, the transaction will execute a fallback or zero transfer and revert, because no function call (such as `exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))`) is ABI-encoded into the calldata!
2. **Missing ERC-20 Approval Transaction**:
   - Swapping an ERC-20 token (such as USDC, ARB, or WETH) on Uniswap v3 requires an `approve(router_address, amount)` transaction prior to executing `exactInputSingle`. `dex_router.py` provides `build_approval_transaction()`, but `app.js` does not check allowance or prompt an approval transaction in MetaMask.
3. **Synthetic / Mock Hash Generation in Headless Bridge Mode (`visualization/server/app.py:227-232` & `execution/wallet/eip1193_bridge.py:300-302`)**:
   - If `window.ethereum` is not present, or if `/rpc` `eth_sendTransaction` is called directly, the backend generates a synthetic UUID/hex string (`0xaaaa...` or `0xuuid...`) and marks it as confirmed immediately, rather than executing on-chain.
4. **DualEngineWalletRouter Staging vs Execution Split (`execution/wallet/router.py:107-128`)**:
   - When called programmatically via `DualEngineWalletRouter.execute_swap(..., signer_mode="eip1193_metamask")`, the router stages the request in `bridge_server`, but then immediately broadcasts a dummy raw transaction string (`0xRAW_SIGNED_TX_...`) through `self._send_raw_transaction()`, rather than waiting for asynchronous MetaMask signing by a human user.
5. **No Automated Loop for Target Wallet Balance ($20 Target)**:
   - The repository contains `evm_ten_trade_runner.py` for simulated 10-trade micro-capital runs ($2.00 ETH starting balance), but does not have a live automated controller that polls the connected MetaMask wallet balance on-chain via `eth_getBalance` and re-triggers trades until the balance reaches $20.00.

---

## 2. Logic Chain

1. **Connection Logic**:
   - Observation: `app.js:438` checks `window.ethereum` and calls `eth_requestAccounts` + `eth_chainId`.
   - Observation: Upon receiving the user's public address and chain ID, it posts to `/rpc` with `wallet_syncAccount`.
   - Observation: `app.py:210` updates `bridge_server.connected_accounts` and `bridge_server.chain_id`.
   - Inference: The bridge server does NOT hold the user's private key; it relies on the browser extension as an interactive EIP-1193 provider.

2. **Execution & Signing Logic**:
   - Observation: `app.js:520` stages the transaction on `/send-transaction` to receive a `request_id`.
   - Observation: `app.js:538` calls `window.ethereum.request({ method: 'eth_sendTransaction', params: [ethTxParams] })`.
   - Observation: Once signed by the user in MetaMask, `window.ethereum` returns the broadcast transaction hash.
   - Observation: `app.js:565` reports the hash back to `/confirm-transaction`.
   - Inference: Live execution is designed as human-in-the-loop ("Frontier Mode"), where MetaMask handles private key signature and RPC broadcast, and the backend tracks staging and confirmations.

3. **Live Execution Failure Mechanism**:
   - Observation: In `app.js:536`, `data` is set to `'0x'`. In `dex_router.py:137`, `data` is set to `'0x'`.
   - Observation: Uniswap v3 SwapRouter02 requires 4-byte selector and ABI-encoded tuple for `exactInputSingle` (selector `0x04e45aaf` or `0x414bf382`).
   - Inference: If a user confirms the swap in MetaMask right now, the transaction will send 0 ETH to the contract with empty data, resulting in either a revert or an unexecuted swap.
   - Observation: No approval transaction is initiated for ERC-20 input tokens.
   - Inference: Even if calldata was present, swapping non-native tokens would revert due to `STF` (SafeTransferFrom / insufficient allowance).

4. **Simulation vs Live Pipeline**:
   - Observation: `evm_ten_trade_runner.py` and `tests/e2e/harness.py` test realistic simulated pipelines using `MockWeb3Provider` and `_L2Web3ProviderAdapter`, with probe to live RPCs for base fee.
   - Inference: The mathematical, risk, and guardrail models (GoPlus, ATR sizing, Slippage, Gas ceiling, eth_call) are fully functional and pass 100% of test suites, but the live frontend bridge contains incomplete calldata serialization for the actual DEX contracts.

---

## 3. Caveats

1. **Read-Only Scope**: In accordance with the system constraints, no code modifications or live transactions were executed during this investigation.
2. **MetaMask Browser Extension Dependency**: The EIP-1193 bridge requires a human user operating a desktop browser with MetaMask. Headless CLI agents cannot interact directly with MetaMask unless an external automation driver (e.g. Playwright with extension loading) or the alternative `hot_keystore` signer (`HotKeystoreSigner` with private key) is used.
3. **Network Gas Funds**: Executing live trades on Arbitrum One or Base requires native ETH in the connected wallet to pay for L2 gas.

---

## 4. Conclusion & Recommendations

### Summary of Survey Findings:
1. **Connection Flow**: The platform connects to MetaMask via standard `window.ethereum.request` in the browser UI, synchronizing the active account and chain ID to the FastAPI bridge server via `/rpc` (`wallet_syncAccount`).
2. **Transaction Flow**: Trades are constructed by multi-agent deliberation, evaluated by the 5-layer safety guardrail pipeline, staged via `/send-transaction`, sent to MetaMask via `eth_sendTransaction`, and acknowledged via `/confirm-transaction`.
3. **Configured Networks & Pairs**: Configured for Arbitrum One (42161) and Base (8453), with canonical Uniswap v3 SwapRouter02 and Aerodrome contracts, and pairs including WETH/USDC, WETH/WBTC, WETH/ARB, WETH/GMX, WETH/PENDLE, WETH/AERO, and WETH/cbBTC.
4. **Runtime Process**: Requires `python run_live_metamask_terminal.py` running on `localhost:8899`, an active browser session with MetaMask connected, and real-world market price streaming.
5. **Key Gaps for Live Trading**:
   - `visualization/web/static/js/app.js` needs ABI calldata encoding for Uniswap v3 `exactInputSingle` instead of empty `data: '0x'`.
   - ERC-20 `approve()` check and prompt must precede the swap transaction.
   - For automated execution until wallet balance reaches $20, an on-chain balance polling watcher (querying `eth_getBalance` on the RPC) and a trade iteration controller are required.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify Router & Network Configurations**:
   ```powershell
   python -m pytest tests/unit/test_execution.py -k "TestMultiDEXRouter or TestEIP1193BridgeServer"
   ```
2. **Inspect Code Locations Directly**:
   - Calldata definition: inspect `visualization/web/static/js/app.js` line 536.
   - Contract addresses: inspect `execution/routers/dex_router.py` lines 31-59.
   - Bridge staging & RPC: inspect `execution/wallet/eip1193_bridge.py` lines 226-324 and `visualization/server/app.py` lines 201-246.
   - Live terminal runner: inspect `run_live_metamask_terminal.py` lines 150-212.
3. **Invalidation Conditions**:
   - If `app.js` is updated with full ABI encoding (e.g. ethers.js / web3.js encoding of `exactInputSingle`), the calldata gap is resolved.
   - If `DualEngineWalletRouter` in `hot_keystore` mode is used with a funded local keystore instead of interactive MetaMask, fully headless autonomous execution is achieved without browser interaction.
