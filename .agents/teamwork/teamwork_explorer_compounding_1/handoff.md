# Handoff Report: Requirement R1 (Micro-Capital Trading and Compounding Execution)

**Explorer**: Explorer 1 (`teamwork_explorer_compounding_1`)  
**Mission**: Codebase investigation of micro-capital trading initialization, balance management (0.0012 ETH / ~$3.74 USD), fractional capital allocation, and compounding loop execution toward the $2,000 USD target valuation under fully autonomous execution authorization.  
**Date**: 2026-11-09T01:35:00Z  

---

## 1. Observation

Direct observations from the codebase across `core/`, `crypto_pipeline/sizing/`, `simulation/paper_trader/`, `execution/`, and `visualization/`:

### 1.1 Existing Position Sizing Logic (`crypto_pipeline/sizing/atr_sizer.py`)
- **Lines 46–98**: `ATRSizingEngine.calculate_atr14_sizing(...)` uses fixed-fractional risk allocation:
  ```python
  dollar_risk = portfolio_value_usd * risk_pct_budget
  stop_distance = atr_14 * multiplier
  raw_position_size = dollar_risk / stop_distance
  recommended_position_usd = raw_position_size * price
  ```
- **Lines 49–53**: Method signature defaults:
  - `portfolio_value_usd: float = 10000.0`
  - `risk_pct_budget: float = 0.01` (1% risk)
  - `multiplier: float = 1.5`
  - `max_notional_cap_usd: float = 250.0`
- **Observed Limitation for Micro-Capital**: With a starting balance of 0.0012 ETH (~$3.74 USD), a 1% risk budget produces `dollar_risk = $0.0374`. Divided by an ATR stop distance, `raw_position_size` is sub-microscopic and cannot pass exchange precision rules (`self.exchange.amount_to_precision`). A dedicated micro-capital allocation mode is required.

### 1.2 Safety Guardrail Allocations and Gas Ratio Limits (`execution/guardrails/pipeline.py`)
- **Lines 37–49**: `PreBroadcastGuardrailPipeline.__init__` establishes default safety parameters:
  ```python
  max_spend_per_trade_usd: float = 250.0
  max_asset_concentration_pct: float = 20.0
  max_daily_drawdown_pct: float = 8.0
  eth_price_usd: float = 3100.0
  ```
- **Lines 166–174 (Layer 2 Capital Allocation)**:
  ```python
  new_asset_total = current_asset_holdings_usd + request.trade_value_usd
  concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0 if current_portfolio_value_usd > 0 else 100.0
  if concentration_pct > self.max_asset_concentration_pct:
      return GuardrailVerdict(
          approved=False,
          rejection_reason=f"Layer 2 Asset concentration {concentration_pct:.1f}% exceeds max {self.max_asset_concentration_pct}%.",
          layer_failed="Layer 2: Capital Allocation",
      )
  ```
  *Impact*: With `portfolio_value = $3.74`, enforcing `max_asset_concentration_pct = 20.0%` caps any single trade at `$0.748 USD`. This forces unviable position sizes.
- **Lines 241–250 (Layer 4 Gas & Congestion)**:
  ```python
  simulated_gas = 145000
  gas_cost_usd = (simulated_gas * (base_fee_gwei + priority_fee_gwei) * 1e-9) * self.eth_price_usd
  gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0 if request.trade_value_usd > 0 else float('inf')
  if gas_ratio_pct > self.config.gas_cost_ratio_max_pct:
      return GuardrailVerdict(approved=False, ...)
  ```
  *Impact*: In `tests/e2e/contracts.py:141`, `gas_cost_ratio_max_pct = 1.5%`. On L2 (Base / Arbitrum), gas costs ~$0.015–$0.025 USD. For a `$0.74` trade, gas ratio is ~2.7%–3.3% (tripping Layer 4). For a `$2.50–$3.20` trade, gas ratio is ~0.5%–0.8% (passing Layer 4 cleanly).

### 1.3 Micro-Capital EVM Sizing & Compounding Precedent (`simulation/paper_trader/evm_ten_trade_runner.py`)
- **Lines 205–209**: Establishes a native gas reserve for micro-capital:
  ```python
  reserved_gas_usd = 0.16  # ~8% of the $2.00 wallet ($0.16 = 0.00005128 ETH)
  reserved_gas_eth = round(reserved_gas_usd / eth_price_usd, 8)
  ```
- **Lines 257–258**: Relaxes concentration specifically for micro-capital single-position rotation:
  ```python
  max_spend_per_trade_usd=2.50,
  max_asset_concentration_pct=98.0,  # single active position rotation on micro-account
  ```
- **Lines 498–501**: Calculates deployable capital:
  ```python
  deployable_usd = round(max(0.50, wallet_usd - reserved_gas_usd), 4)
  eth_in = round(deployable_usd / eth_price_usd, 8)
  amount_in_wei = int(eth_in * 1e18)
  ```
- **Lines 576–578**: Compounding equity update:
  ```python
  wallet_usd = round(wallet_usd + net_pnl_usd, 4)
  wallet_eth = round(wallet_usd / eth_price_usd, 8)
  equity_curve.append(wallet_usd)
  ```

### 1.4 MetaMask Balance Ingestion and Sync (`visualization/server/app.py` & `visualization/web/static/js/app.js`)
- **`app.js` (Lines 448–465)**:
  MetaMask extension retrieves wallet balance via `window.ethereum.request({ method: 'eth_getBalance' })`, converts hex wei to ETH (`balEth`), and posts to `/wallet_syncAccount`:
  ```javascript
  return fetch('/wallet_syncAccount', {
      method: 'POST',
      headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ account: connectedWalletAddress, chain_id: chainId, balance_eth: balEth })
  });
  ```
- **`app.py` (Lines 247–251 & 301–311)**:
  Both the JSON-RPC `/rpc` handler and direct `/wallet_syncAccount` parse `balance_eth` and store it:
  ```python
  app.state.bridge_server.wallet_balance_eth = max(0.0, float(balance_eth))
  ```

### 1.5 Terminal Loop Defect for Micro-Capital (`run_live_metamask_terminal.py`)
- **Lines 245–255**:
  ```python
  wallet_eth = getattr(bridge, "wallet_balance_eth", 0.0)
  eth_spot = latest_computations.get("ETH/USDT", {}).get("live_px", 3120.0)

  if wallet_eth > 0.015:
      deployable_eth = wallet_eth - 0.015
      alloc_fraction = 0.45 if t_adx.adx_14 >= 22.0 else 0.35
      trade_usd = round(deployable_eth * alloc_fraction * eth_spot, 2)
      trade_usd = max(25.0, min(trade_usd, 500.0))
  else:
      trade_usd = 40.0
  ```
- **Critical Flaw**: For 0.0012 ETH (~$3.74 USD), `wallet_eth > 0.015` evaluates to `False`. The `else` branch assigns `trade_usd = 40.0`, which is >10x the user's entire wallet balance ($3.74).

### 1.6 Bridge Status and Profit Target Tracking (`execution/wallet/eip1193_bridge.py`)
- **Lines 69–78 & 121–123**: `BridgeStatus` and `EIP1193BridgeServer` already define the target:
  ```python
  wallet_balance_eth: float = 0.0
  cumulative_profit_usd: float = 0.0
  target_profit_usd: float = 2000.0
  ```
- **Lines 317–319**: `/rpc` handles `eth_sendTransaction` autonomously by staging and confirming with synthetic hash, allowing autonomous order routing.

### 1.7 Direct User Authorization for Full Autonomy (`ORIGINAL_REQUEST.md`)
- **Lines 45–50**: The user authorized:
  > *"do everything autonomus , ineed 2000 $ , you have all my confirmation to buy and sell just do it now ,"*
  The engine is authorized to run continuously without waiting for human confirmation on every trade.

---

## 2. Logic Chain

1. **Starting Balance Initialization**:
   - The user's MetaMask wallet holds 0.0012 ETH. At current ETH spot (~$3,120 USD), the starting capital is `$3.744 USD`.
   - When MetaMask connects, `app.js` calls `eth_getBalance` and POSTs `{ "balance_eth": 0.0012 }` to `/wallet_syncAccount`.
   - `visualization/server/app.py` writes this to `bridge.wallet_balance_eth = 0.0012`. In headless or automated execution, this is initialized directly via `bridge.wallet_balance_eth = 0.0012` or `PaperTradingEngine(initial_cash_usd=3.744)`.

2. **Native Gas Reserve Calculation**:
   - On Layer 2 (Base or Arbitrum), gas costs ~$0.015–$0.025 per DEX swap.
   - Reserving a dynamic buffer of `min(0.0001 ETH, wallet_eth * 0.08)` (~$0.31 USD) ensures the account never runs out of native gas for swaps, approvals, and speedups.
   - Deployable capital = `0.0012 - 0.0001 = 0.0011 ETH` (~`$3.43 USD`).

3. **Fractional Capital Allocation (Micro vs. Growth Tiers)**:
   - *Micro Tier (Equity < $25 USD)*: Splitting $3.43 across multiple positions causes gas fees (~$0.02) to eat >2.5% of trade value, failing the 1.5% gas-to-trade guardrail. Therefore, the strategy must deploy **70% to 85%** of deployable capital into a single active rotating position (~$2.40 to $2.90 USD). For a $2.80 trade, $0.02 gas is 0.71% of trade value (well within the 1.5% ceiling).
   - *Growth Tier (Equity >= $25 to $2,000 USD)*: As equity scales past $25, the engine transitions dynamically into multi-asset ATR-14 volatility sizing (`ATRSizingEngine`) with a 1%–2% risk budget and a 20% asset concentration cap.

4. **Safety Guardrail Harmonization**:
   - In `PreBroadcastGuardrailPipeline`, `max_asset_concentration_pct` must be scaled dynamically:
     - When `portfolio_value_usd < 25.0`: `max_asset_concentration_pct = 95.0%`
     - When `portfolio_value_usd >= 25.0`: `max_asset_concentration_pct = 20.0%`
   - This prevents Layer 2 from rejecting micro-capital trades while maintaining institutional concentration protection once the portfolio grows.

5. **Compounding Loop Execution without Premature Halting**:
   - Each closed round-trip trade realizes PnL: `net_pnl_usd = gross_pnl - round_trip_dex_fees - round_trip_l2_gas`.
   - Realized profits are compounded: `wallet_usd += net_pnl_usd` and `wallet_eth = wallet_usd / eth_price_usd`.
   - The loop does **NOT** halt when a trade hits take-profit (+3% to +5%). Instead, take-profit closes the position, adds the realized profit to the cash balance, updates `cumulative_profit_usd`, and immediately triggers the next scan cycle.
   - The compounding loop continues until `current_equity_usd >= 2000.0` or until a daily drawdown circuit breaker (8%) is triggered.

6. **Fully Autonomous Execution**:
   - Per user directive, the dual-engine router (`DualEngineWalletRouter`) and bridge server (`EIP1193BridgeServer`) must operate in auto-broadcast mode, dispensing with manual browser confirmation dialogs.

---

## 3. Caveats

1. **Market Slippage & Low Liquidity**: Micro trades must only execute on deep L2 pools (e.g., WETH/USDC, WETH/ARB, WETH/cbBTC, WETH/AERO) where pool fees are 5 bps and price impact is < 0.10%. Illiquid memecoins would erode capital through slippage.
2. **Compounding Trajectory**: Growing $3.74 to $2,000 USD is a ~534x expansion. At an average net gain of +3.5% per round-trip, this requires approximately 180 profitable compounding cycles with high win-rate discipline (trailing ATR stops). It cannot occur in a single trade.
3. **RPC Rate Limits**: Continuous autonomous querying of public L2 RPC nodes requires handling HTTP 429 backoff gracefully, as implemented in `evm_ten_trade_runner.py:177–194`.

---

## 4. Conclusion

The platform possesses the core infrastructure for micro-capital trading and compounding, but requires three specific parameter and wiring enhancements:

1. **Fix `run_live_metamask_terminal.py` sizing logic**:
   Replace the hardcoded `wallet_eth > 0.015` check and `$40.00` fallback with dynamic micro-capital sizing:
   - Gas reserve: `min(0.0001 ETH, wallet_eth * 0.08)` (~$0.31 USD).
   - Deployable capital: `wallet_eth - gas_reserve`.
   - Allocation: 75%–85% of deployable capital when equity < $25; standard ATR-14 sizing when equity >= $25.
2. **Harmonize `PreBroadcastGuardrailPipeline` concentration cap**:
   Adjust `max_asset_concentration_pct` dynamically based on portfolio equity: 95% for equity < $25, scaling down to 20% for equity >= $25.
3. **Wire Continuous Autonomous Compounding Engine**:
   Connect the live market indicator loop (`compute_rsi`, `compute_adx`, `compute_macd`) with order execution (`MultiDEXRouter` + `DualEngineWalletRouter`), reinvesting 100% of realized profits back into subsequent trade allocations until reaching the $2,000 USD valuation target.

---

## 5. Verification Method

### 5.1 Verification Commands
1. **Live Terminal and Bridge Verification Harness**:
   ```powershell
   python tests/verify_live_terminal_metamask.py
   ```
   *Expected Result*: 8/8 tests pass (100% operational).
2. **EVM Micro-Capital 10-Trade On-Chain Simulator**:
   ```powershell
   python simulation/paper_trader/evm_ten_trade_runner.py
   ```
   *Expected Result*: Demonstrates real-world micro-capital ($2.00 ETH) execution on Arbitrum and Base, showing 100% guardrail pass rate, trailing ATR stop-losses, and net compounding profit.
3. **100/200-Trade AI Accuracy & Compounding Backtest**:
   ```powershell
   python simulation/paper_trader/hundred_trade_runner.py
   ```
   *Expected Result*: Demonstrates compounding loop from micro-capital to growth equity without premature halting.

### 5.2 Files to Inspect
- `crypto_pipeline/sizing/atr_sizer.py` (lines 46–98)
- `execution/guardrails/pipeline.py` (lines 37–49, 159–180, 241–250)
- `run_live_metamask_terminal.py` (lines 244–279)
- `simulation/paper_trader/evm_ten_trade_runner.py` (lines 205–271, 498–625)
- `execution/wallet/eip1193_bridge.py` (lines 69–78, 121–123, 303–320)

### 5.3 Invalidation Conditions
- Any code changes that cause `tests/verify_live_terminal_metamask.py` to fail.
- Allocation sizes exceeding total available wallet balance.
- Gas costs exceeding 1.5% of trade value on L2 networks.
