# Quantitative Trading Strategy, Feasibility, Risk Management & System Architecture Specification
## Cross-Asset Rotation on Arbitrum One via Uniswap v3 (WBTC / WETH / ARB / LINK / USDC)

---

### Document Metadata
- **System**: Antigravity Agentic Trading Platform — Quantitative Strategy Engine
- **Target Network**: Arbitrum One (Chain ID: `42161`)
- **Execution Protocol**: Uniswap v3 (`SwapRouter02: 0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`, `QuoterV2: 0x61fFE014bA17989E743c5F6cB21bF9697530B21e`)
- **Target Universe**:
  - **WBTC**: `0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f` (8 decimals)
  - **WETH**: `0x82aF49447D8a07e3bd95BD0d56f35241523fBab1` (18 decimals)
  - **ARB**: `0x912CE59144191C1204E64559FE8253a0e49E6548` (18 decimals)
  - **LINK**: `0xf97f4df75117a78c1A5a0DBb814Af92458539FB4` (18 decimals)
  - **USDC**: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` (Circle Native USDC, 6 decimals)
- **Status**: Production Architecture & Engineering Specification
- **Milestone Reference**: Milestone 8 (M-Quant) | Features F39–F44

---

## 1. Executive Summary & System Overview

### 1.1 Executive Summary
This document establishes the definitive quantitative strategy, market microstructure feasibility model, multi-tier risk architecture, and modular software implementation plan for cross-asset trading and capital rotation between Bitcoin (WBTC), Ethereum (WETH), high-beta Arbitrum ecosystem tokens (ARB, LINK), and cash reserves (USDC) on Arbitrum One via Uniswap v3.

The architecture directly addresses three core challenges inherent in decentralized algorithmic trading:
1. **Regime-Dependent Alpha Erosion**: Pure pairs trading and momentum strategies suffer catastrophic drawdowns during crypto macro trend reversals and volatility spikes. We formulate a hierarchical three-layer alpha engine comprising a log-ratio momentum model with rolling Z-score overextension bounds for Core assets (WBTC/WETH), a multi-factor macro regime detection filter ($\mathcal{M}_t$) governing risk-on altcoin rotation (ARB/LINK), and an event-driven, cost-aware drift rebalancer.
2. **Microstructure & Liquidity Fragmentation on Concentrated AMMs**: Uniswap v3 liquidity is tick-concentrated, resulting in non-linear price impact across fee tiers. We benchmark live liquidity depth across 7 pairs on Arbitrum One, establish optimal fee tier selection policies (e.g. 5 bps for majors, 30 bps for alts), and demonstrate that multi-hop routing (`LINK -> WETH -> USDC`) reduces execution slippage by up to $200\times$ relative to thin direct pools.
3. **Execution Safety & L2 Economics**: Post-ArbOS 20 (EIP-4844 blob posting), Arbitrum L2 swap costs have dropped to $\sim \$0.0056 - \$0.0091$, making rebalancing trades as small as $\$10.00$ mathematically viable. To protect capital, all execution is gated through an institutional 5-layer safety pipeline (`PreBroadcastGuardrailPipeline`), dynamic Chandelier trailing stops ($2.5 - 3.0 \times \text{ATR}_{14}$), multi-asset inverse volatility sizing with fat-tail dampened Fractional Kelly ($\lambda_{\text{Kelly}} \le 0.35$), and a three-tier circuit breaker with automated flight-to-USDC protocol.

### 1.2 System Context & Information Flow

The architecture operates as an asynchronous, event-driven state machine where quantitative signals are filtered through risk policies before reaching the on-chain execution router.

```
                              [External Market Feeds]
                     (CCXT: Spot OHLCV, DeFiLlama: TVL, Alt.me: FNG)
                                         │
                                         ▼
                     ┌───────────────────────────────────────┐
                     │      Component 1: Data Ingestion      │
                     │  - Closed-Bar Normalizer (t-1 -> t)   │
                     │  - On-Chain Price Oracles & QuoterV2  │
                     └───────────────────┬───────────────────┘
                                         │ MarketStateSnapshot
                                         ▼
                     ┌───────────────────────────────────────┐
                     │      Component 2: Alpha Engine        │
                     │  Layer A: WBTC/WETH Log-Ratio RMO     │
                     │  Layer B: Altcoin Vol-Adjusted Mom    │
                     │  Macro Regime Detection Filter M_t    │
                     └───────────────────┬───────────────────┘
                                         │ TargetAllocationIntent
                                         ▼
                     ┌───────────────────────────────────────┐
                     │    Component 3: Risk Gating Engine    │
                     │  - Multi-Asset Inverse-Vol & Kelly    │
                     │  - Concentration Limiter (40/35/20)   │
                     │  - Chandelier Trailing Stops & L1-L5  │
                     │  - Multi-Tier Circuit Breakers        │
                     └───────────────────┬───────────────────┘
                                         │ ApprovedRebalanceOrders
                                         ▼
                     ┌───────────────────────────────────────┐
                     │ Component 4: Web3.py Execution Router │
                     │  - Uniswap v3 SwapRouter02 Calldata   │
                     │  - Direct & Multi-Hop Path Optimizer  │
                     │  - EIP-1559 Nonce & Arbitrum Gas Mgr  │
                     └───────────────────┬───────────────────┘
                                         │ Telemetry & Settlement Events
                                         ▼
                     ┌───────────────────────────────────────┐
                     │  Component 5: Telemetry & Persistence │
                     │  - SQLite Ledger & Checkpointing      │
                     │  - SSE/WebSocket Stream to UI         │
                     │  - Circuit Breaker Audit Trails       │
                     └───────────────────────────────────────┘
```

---

## 2. Quantitative Strategy Research & Mathematical Formulations (R1)

All quantitative strategies adhere strictly to the directives of `algorithmic-trading/SKILL.md`:
- **Look-Ahead Bias Elimination**: All signals are evaluated on closed candle $t-1$ and time-shifted (`signal.shift(1)`) for execution at time $t$. No same-bar closing price is consumed for same-bar trade execution.
- **Transaction-Cost Discipline**: Strategies incorporate pool fees (5 bps / 30 bps), QuoterV2 price impact, and Arbitrum sequencer gas.
- **Walk-Forward Integrity**: Parameter search spaces are bounded and designed for out-of-sample rolling calibration rather than full-sample curve fitting.

### 2.1 Layer A: WBTC/WETH Ratio Momentum & Pair Cross-Trading Engine

#### 2.1.1 Continuous Log-Ratio State Variable
Let $P_t^{\text{WBTC}}$ and $P_t^{\text{WETH}}$ denote spot closing prices at bar $t$. To avoid asymmetric scaling artifacts inherent in linear price ratios ($R_t = P_t^{\text{WBTC}} / P_t^{\text{WETH}}$), the state variable is defined as the natural logarithm:

$$r_t = \ln\left(\frac{P_t^{\text{WBTC}}}{P_t^{\text{WETH}}}\right) = \ln(P_t^{\text{WBTC}}) - \ln(P_t^{\text{WETH}})$$

The single-period log-return of the ratio is:

$$\rho_t = r_t - r_{t-1} = \Delta \ln(P_t^{\text{WBTC}}) - \Delta \ln(P_t^{\text{WETH}})$$

Mathematical properties:
- $\rho_t > 0 \iff$ WBTC outperforms WETH over interval $[t-1, t]$.
- $\rho_t < 0 \iff$ WETH outperforms WBTC over interval $[t-1, t]$.
- Inversion symmetry: $\ln(P^{\text{WETH}} / P^{\text{WBTC}}) = -r_t$.

#### 2.1.2 Dual-Speed Ratio Momentum Oscillator (RMO)
To filter high-frequency liquidity noise while isolating medium-term macro capital rotation between Bitcoin and Ethereum, we apply dual Exponential Moving Averages (EMA) to $r_t$:

$$\text{EMA}_{\text{fast}, t}(r) = \alpha_{\text{fast}} r_t + (1 - \alpha_{\text{fast}}) \text{EMA}_{\text{fast}, t-1}(r), \quad \alpha_{\text{fast}} = \frac{2}{N_{\text{fast}} + 1}$$

$$\text{EMA}_{\text{slow}, t}(r) = \alpha_{\text{slow}} r_t + (1 - \alpha_{\text{slow}}) \text{EMA}_{\text{slow}, t-1}(r), \quad \alpha_{\text{slow}} = \frac{2}{N_{\text{slow}} + 1}$$

Default parameters: $N_{\text{fast}} = 12$ bars, $N_{\text{slow}} = 48$ bars (evaluated on 4-hour candles, corresponding to 2 days vs 8 days).

The raw Ratio Momentum Oscillator ($\text{RMO}_t$) and its smoothed Signal Line are defined as:

$$\text{RMO}_t = \text{EMA}_{\text{fast}, t}(r) - \text{EMA}_{\text{slow}, t}(r)$$

$$\text{Signal}_t = \alpha_{\text{sig}} \text{RMO}_t + (1 - \alpha_{\text{sig}}) \text{Signal}_{t-1}, \quad \alpha_{\text{sig}} = \frac{2}{N_{\text{sig}} + 1} \quad (N_{\text{sig}} = 9)$$

$$\Delta \text{RMO}_t = \text{RMO}_t - \text{Signal}_t$$

#### 2.1.3 Rolling Z-Score Overextension & Mean-Reversion Bounds
While crypto pairs trend strongly during market expansions, extreme overextension of the WBTC/WETH ratio consistently experiences violent mean reversion. We construct a rolling window $W_z = 180$ bars (30 days of 4h bars):

$$\mu_t(r) = \frac{1}{W_z} \sum_{i=0}^{W_z - 1} r_{t-i}$$

$$\sigma_t(r) = \sqrt{\frac{1}{W_z - 1} \sum_{i=0}^{W_z - 1} \left(r_{t-i} - \mu_t(r)\right)^2}$$

The rolling Z-score is:

$$Z_t = \frac{r_t - \mu_t(r)}{\sigma_t(r)}$$

To prevent chasing momentum at statistical extremes, we introduce an overextension dampener $\psi(Z_t) \in [0, 1]$:

$$\psi(Z_t) = \begin{cases}
1.0 & \text{if } |Z_t| \le Z_{\text{entry}} \\
\max\left(0.0, \, 1.0 - \frac{|Z_t| - Z_{\text{entry}}}{Z_{\text{cap}} - Z_{\text{entry}}}\right) & \text{if } Z_{\text{entry}} < |Z_t| \le Z_{\text{cap}} \\
0.0 & \text{if } |Z_t| > Z_{\text{cap}}
\end{cases}$$

Parameter specifications:
- $Z_{\text{entry}} = 1.50$ (momentum begins tapering).
- $Z_{\text{cap}} = 2.25$ (hard freeze: momentum signal dampened to zero to protect against exhaustion tops).

#### 2.1.4 Composite Relative Strength Signal ($S_t^{\text{ratio}}$)
Combining normalized trend momentum and overextension damping (strictly shifted by 1 bar to eliminate look-ahead bias):

$$S_t^{\text{ratio}} = \tanh\left( \lambda_1 \frac{\text{RMO}_{t-1}}{\sigma_{t-1}(r)} + \lambda_2 \frac{\Delta \text{RMO}_{t-1}}{\sigma_{t-1}(r)} \right) \cdot \psi(Z_{t-1})$$

where scaling constants $\lambda_1 = 2.0$ and $\lambda_2 = 1.0$.

Properties:
- $S_t^{\text{ratio}} \in [-1.0, +1.0]$.
- $S_t^{\text{ratio}} > 0 \implies$ WBTC displays relative strength $\implies$ Overweight WBTC.
- $S_t^{\text{ratio}} < 0 \implies$ WETH displays relative strength $\implies$ Overweight WETH.
- $S_t^{\text{ratio}} \approx 0 \implies$ Ratio neutral $\implies$ Equal weight within Core.

#### 2.1.5 Target Allocation Within Core Portfolio
Let $w_{\text{core}, t}^*$ denote the total portfolio weight allocated to Core assets (WBTC + WETH). The unconstrained target weights within Core are:

$$w_{\text{WBTC}, t}^{\text{core}*} = 0.50 + 0.50 \cdot S_t^{\text{ratio}} \cdot \Omega_{\max}$$

$$w_{\text{WETH}, t}^{\text{core}*} = 1.0 - w_{\text{WBTC}, t}^{\text{core}*}$$

where $\Omega_{\max} = 0.60$ is the active tilt bound.

This restricts Core allocations to:

$$w_{\text{WBTC}, t}^{\text{core}*} \in [0.20, 0.80], \quad w_{\text{WETH}, t}^{\text{core}*} \in [0.20, 0.80]$$

Neither major asset is ever completely liquidated within Core during normal rotation, preserving liquidity and dampening turnover friction.

---

### 2.2 Layer B: Multi-Factor Risk-On Altcoin Rotation Engine (ARB, LINK)

Altcoins ARB and LINK exhibit high market beta ($\beta \approx 1.5 - 2.2$) relative to Bitcoin. Rotation into altcoins is strictly conditional upon favorable macro market conditions; in neutral or risk-off regimes, altcoin allocation is clamped to zero.

#### 2.2.1 Multi-Factor Macro Regime Filter ($\mathcal{M}_t \in [0, 1]$)
The macro regime filter evaluates three orthogonal market conditions on daily closing data:

1. **Trend Condition ($\mathcal{T}_t$)**:
   $$\mathcal{T}_t = \mathbb{I}\left(P_{t-1}^{\text{BTC}} > \text{SMA}_{200}(P^{\text{BTC}})_{t-1}\right) \times \mathbb{I}\left(\text{SMA}_{50}(P^{\text{BTC}})_{t-1} > \text{SMA}_{200}(P^{\text{BTC}})_{t-1}\right)$$
   Binary gate: If BTC is below its 200-day simple moving average or under a death cross ($\text{SMA}_{50} \le \text{SMA}_{200}$), $\mathcal{T}_t = 0$.

2. **Market Volatility Condition ($\mathcal{V}_t$)**:
   High realized volatility indicates liquidity withdrawal and cascading liquidations. Let 30-day annualized realized volatility of BTC be:
   $$\sigma_{\text{ann}, t-1}^{\text{BTC}} = \sqrt{365} \times \sqrt{\frac{1}{29}\sum_{i=1}^{30}\left(\ln\frac{P_{t-i}^{\text{BTC}}}{P_{t-i-1}^{\text{BTC}}} - \bar{\mu}_{\text{BTC}}\right)^2}$$
   $$\mathcal{V}_t = \begin{cases}
   1.0 & \text{if } \sigma_{\text{ann}, t-1}^{\text{BTC}} \le 0.60 \text{ (low/normal volatility)} \\
   \frac{0.75 - \sigma_{\text{ann}, t-1}^{\text{BTC}}}{0.75 - 0.60} & \text{if } 0.60 < \sigma_{\text{ann}, t-1}^{\text{BTC}} \le 0.75 \\
   0.0 & \text{if } \sigma_{\text{ann}, t-1}^{\text{BTC}} > 0.75 \text{ (volatility shock cap)}
   \end{cases}$$

3. **Market Breadth & Sentiment Condition ($\mathcal{B}_t$)**:
   Using the Alternative.me Fear & Greed Index ($\text{FNG} \in [0, 100]$):
   $$\mathcal{B}_t = \begin{cases}
   0.0 & \text{if } \text{FNG}_{t-1} < 25 \text{ (Extreme Fear)} \\
   \frac{\text{FNG}_{t-1} - 25}{50 - 25} & \text{if } 25 \le \text{FNG}_{t-1} < 50 \\
   1.0 & \text{if } \text{FNG}_{t-1} \ge 50 \text{ (Neutral to Greed)}
   \end{cases}$$

**Composite Macro Regime Score**:

$$\mathcal{M}_t = \mathcal{T}_t \times \mathcal{V}_t \times \mathcal{B}_t \quad \in [0.0, 1.0]$$

Classification rules:
- $\mathcal{M}_t \ge 0.70 \implies$ **RISK_ON**: Full altcoin rotation active.
- $0.30 \le \mathcal{M}_t < 0.70 \implies$ **NEUTRAL**: Scaled satellite budget; selective allocation.
- $\mathcal{M}_t < 0.30 \implies$ **RISK_OFF**: Zero altcoins allowed ($w_{\text{sat}}^* = 0$). Capital reallocated to Core and USDC.

#### 2.2.2 Altcoin Cross-Sectional Momentum & Relative Strength Ranking
For each candidate altcoin $i \in \{\text{ARB}, \text{LINK}\}$:

1. **Multi-Horizon Rate of Change ($\text{ROC}_{i}$)**:
   $$\text{ROC}_{i, \tau, t-1} = \frac{P_{i, t-1} - P_{i, t-1-\tau}}{P_{i, t-1-\tau}}$$
   $$\text{Mom}_{i, t} = 0.50 \cdot \text{ROC}_{i, 7\text{d}, t-1} + 0.30 \cdot \text{ROC}_{i, 21\text{d}, t-1} + 0.20 \cdot \text{ROC}_{i, 60\text{d}, t-1}$$

2. **Downside Volatility Normalization (Sortino Momentum)**:
   $$\sigma_{i, t-1}^{\text{down}} = \sqrt{\frac{1}{N}\sum_{k=1}^N \min\left(0, \ln\frac{P_{i, t-k}}{P_{i, t-k-1}}\right)^2} \times \sqrt{365}$$
   $$\text{AdjMom}_{i, t} = \frac{\text{Mom}_{i, t}}{\max\left(0.20, \, \sigma_{i, t-1}^{\text{down}}\right)}$$

3. **Relative Strength vs. WETH ($\text{RS}_{i, t}$)**:
   Because altcoins primarily trade against ETH liquidity on Arbitrum:
   $$\text{RS}_{i, t} = \frac{P_{i, t-1} / P_{t-1}^{\text{WETH}}}{\text{SMA}_{30}\left(P_i / P^{\text{WETH}}\right)_{t-1}} - 1.0$$

4. **Composite Altcoin Score**:
   $$\text{Score}_{i, t} = 0.60 \cdot \text{AdjMom}_{i, t} + 0.40 \cdot \text{RS}_{i, t}$$

#### 2.2.3 Satellite Allocation Sizing
The maximum satellite portfolio budget is bounded by:

$$w_{\text{sat}, t}^* = w_{\text{sat}}^{\max} \times \mathcal{M}_t, \quad \text{where } w_{\text{sat}}^{\max} = 0.30 \quad (30\%)$$

For individual assets:

$$\tilde{w}_{i, t} = \begin{cases}
\max\left(0.0, \, \text{Score}_{i, t}\right) & \text{if } \text{Score}_{i, t} > 0.05 \text{ and } P_{i, t-1} > \text{SMA}_{50}(P_i)_{t-1} \\
0.0 & \text{otherwise}
\end{cases}$$

If $\sum_j \tilde{w}_{j, t} > 0$:

$$w_{i, t}^* = \min\left(0.20, \, w_{\text{sat}, t}^* \times \frac{\tilde{w}_{i, t}}{\sum_j \tilde{w}_{j, t}}\right)$$

The hard constraint $w_{i, t}^* \le 0.20$ guarantees strict compliance with **Guardrail L2 (20% maximum single asset concentration)**. Any unallocated satellite capacity rolls back into the Core portfolio.

---

### 2.3 Layer C: Cost-Aware Drift Rebalancing Engine

To prevent excessive turnover and fee bleed on DEX pools, rebalancing is triggered by drift thresholds rather than fixed calendar frequencies.

#### 2.3.1 Drift Metrics & Rebalance Triggers
Let portfolio value at bar $t$ across $K$ assets be $V_t = \sum_{k=1}^K q_{k, t} P_{k, t}$, actual weight $w_{k, t} = \frac{q_{k, t} P_{k, t}}{V_t}$, and target weight $w_{k, t}^*$.
- Individual asset drift: $\delta_{k, t} = |w_{k, t} - w_{k, t}^*|$.
- Aggregate portfolio drift: $\Delta_{\text{port}, t} = \frac{1}{2} \sum_{k=1}^K |w_{k, t} - w_{k, t}^*|$.

**Trigger Conditions**: Rebalance occurs if:
1. **Asset Drift Threshold**: $\exists k \text{ s.t. } \delta_{k, t} \ge \delta_{\text{asset\_max}} = 0.05$ (5.0%).
2. **Aggregate Drift Threshold**: $\Delta_{\text{port}, t} \ge \Delta_{\text{port\_max}} = 0.08$ (8.0%).
3. **Calendar Fallback**: Elapsed time $t - t_{\text{last\_rebal}} \ge 7 \text{ days}$ and $\Delta_{\text{port}, t} \ge 0.03$.

#### 2.3.2 Transaction Cost Gate & Order Chunking
For target trade notional $\Delta N_k = |w_{k, t} - w_{k, t}^*| \times V_t$:
- If $\Delta N_k < \$50.00$: Order discarded as uneconomic dust.
- If $\Delta N_k > \$250.00$: Sliced into discrete $\$250.00$ sub-orders executed across consecutive blocks to strictly satisfy **Guardrail L2 per-trade spend limit**.

The round-trip execution friction for swap $k$ is:

$$C_k = \Delta N_k \times \left( f_{\text{pool}, k} + \text{Slippage}_{\text{est}, k} \right) + \text{GasCost}_{\text{USD}}$$

The swap is approved if and only if the cost-to-rebalance ratio satisfies:

$$\frac{C_k}{\Delta N_k} \le \Phi_{\text{cost\_max}} = 0.010 \quad (1.0\% \text{ maximum friction})$$

---

## 3. Arbitrum Uniswap v3 Execution & Feasibility Modeling (R2)

### 3.1 On-Chain Address Corrections
Through empirical inspection on Arbitrum One Mainnet (Chain ID `42161`), two critical contract address discrepancies in initial specifications were identified and corrected:

1. **Circle Native USDC vs Typo Address**:
   - *Incorrect Dispatch Address*: `0xaf88d065e77c4c4779274291887c063473232247` (returns 0 bytecode; non-existent contract).
   - *Canonical Native USDC*: **`0xaf88d065e77c8cC2239327C5EDb3A432268e5831`** (6 decimals; official Circle contract).
   - *Bridged USDC.e (Legacy)*: `0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8` (6 decimals; bridged from L1).
2. **Canonical Uniswap v3 QuoterV2**:
   - *Codebase Typo*: `0x61fFE014bA136170505655d03170F09287640F16` (0 bytecode on Arbitrum).
   - *QuoterV1 (Legacy)*: `0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6`.
   - *Canonical QuoterV2*: **`0x61fFE014bA17989E743c5F6cB21bF9697530B21e`** (selector `0xc6a5026a`, returns `amountOut`, `sqrtPriceX96After`, `initializedTicksCrossed`, and `gasEstimate`).

### 3.2 Seven-Pair Uniswap v3 Pool Liquidity & Fee Tier Selection Matrix
Queries executed against the Arbitrum One Uniswap v3 Factory (`0x1F98431c8aD98523631AE4a59f267346ea31F984`) produced the verified liquidity mapping below:

| Pair | Fee Tier | Pool Contract Address | Active In-Range Liquidity ($L$) | Current Tick | Routing Classification |
|:---|:---:|:---|:---:|:---:|:---|
| **WBTC / WETH** | 100 (0.01%) | `0x03a3be7ab4aa263d42d63b6cc594f4fb3d3f3951` | $5.68 \times 10^{14}$ | 266,062 | Secondary |
| | **500 (0.05%)** | `0x2f5e87c9312fa29aed5c179e456625d79015299c` | **$2.02 \times 10^{17}$** | 266,024 | **PRIMARY (Dominant)** |
| | 3000 (0.30%) | `0x149e36e72726e0bcea5c59d40df2c43f60f5a22d` | $7.55 \times 10^{14}$ | 266,039 | Low Depth |
| **WETH / USDC** | 100 (0.01%) | `0x6f38e884725a116c9c7fbf208e79fe8828a2595f` | $3.74 \times 10^{15}$ | -200,028 | Stable-peg only |
| | **500 (0.05%)** | `0xc6962004f452be9203591991d15f6b388e09e8d0` | **$2.57 \times 10^{18}$** | -200,026 | **PRIMARY (Arb Backbone)** |
| | 3000 (0.30%) | `0xc473e2aee3441bf9240be85eb122abb059a3b57c` | $4.85 \times 10^{17}$ | -200,042 | Deep Secondary |
| **WBTC / USDC** | **500 (0.05%)** | `0x0e4831319a50228b9e450861297ab92dee15b44f` | **$2.23 \times 10^{12}$** | 66,000 | **PRIMARY Direct** |
| | 3000 (0.30%) | `0x6985cb98ce393fce8d6272127f39013f61e36166` | $1.00 \times 10^{11}$ | 65,984 | Low Depth |
| **ARB / WETH** | **500 (0.05%)** | `0xc6f780497a95e246eb9449f5e4770916dcd6396a` | **$6.20 \times 10^{23}$** | 94,196 | **PRIMARY (Dominant)** |
| | 3000 (0.30%) | `0x92c63d0e701caae670c9415d91c474f686298f00` | $2.41 \times 10^{22}$ | 94,174 | Secondary |
| **LINK / WETH** | 500 (0.05%) | `0x91308bc9ce8ca2db82aa30c65619856cc939d907` | $1.26 \times 10^{22}$ | 52,925 | Deep Secondary |
| | **3000 (0.30%)** | `0x468b88941e7cc0b88c1869d68ab6b570bcef62ff` | **$3.80 \times 10^{22}$** | 52,928 | **PRIMARY (Dominant)** |
| **ARB / USDC** | 500 (0.05%) | `0xb0f6ca40411360c03d41c5ffc5f179b8403cdcf8` | $3.66 \times 10^{17}$ | -294,252 | Moderate |
| | **3000 (0.30%)** | `0xaebdca1bc8d89177ebe2308d62af5e74885dccc3` | **$2.00 \times 10^{18}$** | -294,230 | **PRIMARY Direct ($\le \$5\text{k}$)** |
| **LINK / USDC** | 500 (0.05%) | `0x655c1607f8c2e73d5b4ddabce9ba8792b87592b6` | $8.78 \times 10^{14}$ | 251,649 | Dangerous (Thin) |
| | 3000 (0.30%) | `0xbbe36e6f0331c6a36ab44bc8421e28e1a1871c1e` | $1.94 \times 10^{16}$ | 252,955 | Dangerous (Thin) |
| | **MULTI-HOP** | **LINK $\xrightarrow{3000}$ WETH $\xrightarrow{500}$ USDC** | — | — | **MANDATORY OPTIMAL** |

### 3.3 Empirical Slippage & Multi-Hop Routing Analysis
Using `QuoterV2`, price impact and tick traversals were benchmarked across sizes from $\$100$ to $\$50,000$:

```
+--------------------+----------------+--------------+--------------+---------------+---------------+----------------+
| Route / Pair       | $100 Trade     | $500 Trade   | $1,000 Trade | $5,000 Trade  | $10,000 Trade | $50,000 Trade  |
+--------------------+----------------+--------------+--------------+---------------+---------------+----------------+
| WETH->USDC (500)   | 0.00 bps / 1t  | 0.03 bps / 1t| 0.08 bps / 1t| 0.42 bps / 1t | 0.85 bps / 1t | 4.29 bps / 2t  |
| WBTC->WETH (500)   | 0.00 bps / 1t  | 0.00 bps / 1t| 0.00 bps / 1t| 0.00 bps / 1t | 0.00 bps / 1t | 0.37 bps / 1t  |
| ARB->WETH (500)    | 0.03 bps / 1t  | 0.14 bps / 1t| 1.06 bps / 1t| 2.23 bps / 1t | 3.68 bps / 1t | 15.27 bps / 1t |
| LINK->WETH (3000)  | 0.16 bps / 1t  | 0.81 bps / 1t| 1.62 bps / 1t| 8.08 bps / 1t | 16.15 bps / 1t| 83.90 bps / 4t |
| ARB->USDC (3000)   | 0.38 bps / 0t  | 2.01 bps / 0t| 4.04 bps / 0t| 20.28 bps / 0t| 40.50 bps / 1t| 204.43 bps / 6t|
| WBTC->USDC (500)   | 0.00 bps / 1t  | 0.00 bps / 1t| 0.00 bps / 1t| 0.00 bps / 0t | 0.00 bps / 2t | 7.09 bps / 3t  |
| LINK->USDC Direct  | 14.53 bps / 1t | 66.38 bps / 2t| 119.7 bps / 2t| 663.0 bps / 11t| 3584.6 bps/20t| 8716.8 bps/20t |
+--------------------+----------------+--------------+--------------+---------------+---------------+----------------+
| LINK->WETH->USDC   | 0.16 bps / 2t  | 0.84 bps / 2t| 1.69 bps / 2t| 9.54 bps / 2t | 17.99 bps / 2t| 88.75 bps / 5t |
| (Multi-Hop)        | [90x lower]    | [79x lower]  | [70x lower]  | [69x lower]   | [200x lower]  | [98x lower]    |
+--------------------+----------------+--------------+--------------+---------------+---------------+----------------+
```
*(Notation: `bps` = basis points price impact relative to spot; `t` = initialized ticks crossed).*

**Key Takeaway**: Direct `LINK/USDC` is too illiquid for production algorithmic trades, suffering 120 bps slippage at $\$1\text{k}$ and 8,716 bps at $\$50\text{k}$. Multi-hop routing through WETH drops slippage to **1.69 bps at $\$1\text{k}$ (70x reduction)** and **17.99 bps at $\$10\text{k}$ (200x reduction)**, fully justifying the additional hop gas cost ($\sim \$0.0035$).

### 3.4 Arbitrum L2 Gas Economics & Breakeven Trade Size
Arbitrum One charges execution via ArbOS:

$$\text{GasUsed} = \text{GasUsed}_{\text{L2}} + \text{GasUsed}_{\text{L1}}$$

$$\text{GasUsed}_{\text{L1}} = \frac{\text{L1 Base Fee}}{\text{L2 Base Fee}} \times B_{\text{compressed}} \times 16$$

Under **ArbOS 20 (EIP-4844 blobs)**, L1 batch posting is submitted to Ethereum blobspace, driving total transaction costs down to near pure L2 execution gas:
- Prevailing Arbitrum base fee: $0.0202 \text{ Gwei}$.
- Gas units consumed: Single-hop: $\approx 135,000$ gas; Multi-hop: $\approx 220,000$ gas.
- Dollar cost at $\$2,055 \text{ ETH}$:
  - **Single-Hop**: $135,000 \times 0.0202 \times 10^{-9} \times \$2,055 = \mathbf{\$0.0056}$
  - **Multi-Hop**: $220,000 \times 0.0202 \times 10^{-9} \times \$2,055 = \mathbf{\$0.0091}$

#### Mathematical Breakeven Trade Size ($S_{\min}$)
For an expected alpha return $\mathbb{E}[\alpha]$:

$$\mathbb{E}[\alpha] > \phi + \text{Slippage}(S) + \frac{F_{\text{gas}}}{S} \implies S_{\min} = \frac{F_{\text{gas}}}{\mathbb{E}[\alpha] - \phi - \text{Slippage}}$$

- **Case 1: Core Rotation (WBTC/WETH, Fee = 5 bps, Slippage $\approx 0.01$ bps, Alpha = 100 bps)**:
  $$S_{\min} = \frac{\$0.0056}{0.0100 - 0.0005 - 0.000001} = \frac{\$0.0056}{0.00949} = \mathbf{\$0.59 \text{ USD}}$$
- **Case 2: Satellite LINK Rotation (Multi-hop via WETH, Fee = 35 bps, Slippage = 1.7 bps, Alpha = 100 bps)**:
  $$S_{\min} = \frac{\$0.0091}{0.0100 - 0.0035 - 0.00017} = \frac{\$0.0091}{0.00633} = \mathbf{\$1.44 \text{ USD}}$$

Per **Guardrail L4 constraint** ($\frac{F_{\text{gas}}}{S} \le 1.5\%$):
$$S_{\text{guardrail}} \ge \frac{\$0.0056}{0.015} = \mathbf{\$0.37 \text{ USD}}$$

Even in extreme $10\times$ gas spikes ($0.20 \text{ Gwei}$, $F_{\text{gas}} \approx \$0.06$), the minimum trade size passing Guardrail L4 is only **$\$4.00$**.

---

## 4. Risk Management & Capital Allocation Framework (R3)

### 4.1 Multi-Asset Inverse Volatility Portfolio Sizing
To prevent high-beta altcoins (ARB, LINK) from dominating portfolio variance, risk assets $\mathcal{A}_{\text{active}} \subseteq \{\text{WBTC}, \text{WETH}, \text{ARB}, \text{LINK}\}$ are sized using normalized inverse volatility:

1. **Normalized ATR-14 Volatility**:
   $$\sigma_{i, t}^{\text{norm}} = \frac{\text{ATR}_{i, 14, t}}{P_{i, t}}$$
2. **Inverse Volatility Capital Weight**:
   $$w_i^{\text{inv}} = W_{\text{risk}} \times \frac{\frac{1}{\sigma_{i, t}^{\text{norm}}}}{\sum_{j \in \mathcal{A}_{\text{active}}} \frac{1}{\sigma_{j, t}^{\text{norm}}}}$$

Typical normalized ATRs in crypto markets:
- WBTC: $\sim 2.5\%$
- WETH: $\sim 3.5\%$
- LINK: $\sim 6.5\%$
- ARB: $\sim 7.8\%$

Inverse volatility weighting naturally scales down ARB and LINK to safe fractional exposures.

### 4.2 Fractional Kelly Criterion with Safety Constraints
To budget total risk capital $W_{\text{risk}}$:

1. **Unconstrained Discrete Kelly**:
   Let rolling walk-forward win rate be $p$ and win/loss payoff ratio $b = \overline{W} / \overline{L}$:
   $$f^* = p - \frac{1 - p}{b}$$
2. **Fat-Tail & Kurtosis Dampener**:
   Crypto returns exhibit negative skewness and high kurtosis ($\kappa_{\text{excess}} > 3$). To prevent drawdown ruin:
   $$\lambda_{\text{Kelly}} = \min\left(0.35, \, \frac{1}{2 + \kappa_{\text{excess}}}\right) \le 0.35 \quad (\text{Half-to-Third Kelly})$$
3. **Active Risk Budget**:
   $$W_{\text{risk}} = \max\left(0.0, \, \min\left(\lambda_{\text{Kelly}} \cdot f^*, \, 0.90\right)\right)$$
   If $f^* \le 0$, $W_{\text{risk}} = 0$, enforcing a $100\%$ flight to USDC.

### 4.3 Asset Concentration Tiers
To prevent single-asset failure risk and maintain compliance with Guardrail L2:
- **WBTC Concentration Limit**: $w_{\text{WBTC}} \le 40.0\%$.
- **WETH Concentration Limit**: $w_{\text{WETH}} \le 35.0\%$.
- **Combined Major Core (WBTC + WETH)**: $w_{\text{WBTC}} + w_{\text{WETH}} \le 75.0\%$.
- **Individual Altcoin Ceiling (ARB or LINK)**: $w_{\text{alt}} \le 20.0\%$ (strictly capped by Guardrail L2).
- **Combined Altcoin Satellite Category**: $\sum w_{\text{alt}} \le 30.0\%$.
- **Mandatory Stablecoin Reserve (USDC)**: $w_{\text{USDC}} \ge 10.0\%$ under normal conditions ($w_{\text{USDC}} = 1.0 - \sum w_{\text{risk}}$).

### 4.4 Dynamic Trailing Stops (Chandelier Exit) & Profit Targets
For open positions in asset $i$ entered at bar $t_0$:

1. **Dynamic Chandelier Trailing Stop**:
   $$\text{HighestHigh}(n, t) = \max_{\tau \in [t - n + 1, t]} H_{i, \tau} \quad (n = 22 \text{ bars})$$
   $$\text{TrailingStop}_{i, t} = \max\left(\text{TrailingStop}_{i, t-1}, \, \text{HighestHigh}(n, t) - k_{\text{exit}} \times \text{ATR}_{i, 14, t}\right)$$
   - Core Assets (WBTC, WETH): $k_{\text{exit}} = 3.0$.
   - Satellite Assets (ARB, LINK): $k_{\text{exit}} = 2.5$.
   - *Ratchet invariant*: $\text{TrailingStop}_{i, t} \ge \text{TrailingStop}_{i, t-1}$ ensures stops never loosen.
2. **Hard Initial Catastrophic Stop**:
   $$\text{InitialStop}_i = P_{\text{entry}} \times (1 - \text{MaxLossPct}_i)$$
   where $\text{MaxLossPct} = 5.0\%$ for WBTC/WETH, and $7.5\%$ for ARB/LINK.
3. **Laddered Profit Scaling**:
   - **Tier 1 (+1.5 ATR)**: Liquidate 33% of position into USDC; ratchet stop to entry price $+ 0.5\%$.
   - **Tier 2 (+3.0 ATR)**: Liquidate additional 33% into USDC; trail remaining 34% runner at $1.5 \times \text{ATR}$.

### 4.5 Multi-Tier Circuit Breakers & Emergency Flight to USDC Protocol
Let $V_t$ be mark-to-market equity, $H_t = \max_{s \le t} V_s$ high-water mark, and $V_{\text{open}}$ 00:00 UTC equity:

$$\text{DD}_{\text{daily}, t} = \frac{V_{\text{open}} - V_t}{V_{\text{open}}} \times 100\%, \quad \text{DD}_{\text{cum}, t} = \frac{H_t - V_t}{H_t} \times 100\%$$

| Tier | Trigger Condition | System Action | Recovery Condition |
|:---|:---|:---|:---|
| **Tier 1: Caution Alert** | $\text{DD}_{\text{daily}} \ge 3.0\%$ or $\text{DD}_{\text{cum}} \ge 8.0\%$ | Halve Kelly risk budget ($\lambda \to 0.5 \lambda$). Freeze new altcoin buys. | Drawdown recovers to $< 2.0\%$. |
| **Tier 2: Daily Lockout** | $\text{DD}_{\text{daily}} \ge 5.0\%$ | 24-hour execution lockout. Tighten trailing stops by 40% ($k_{\text{exit}} \to 1.5 \text{ATR}$). | 24h timer expires AND $\text{DD}_{\text{daily}} < 3.0\%$. |
| **Tier 3: Max Drawdown Breaker** | $\text{DD}_{\text{cum}} \ge 15.0\%$ | **EMERGENCY DE-RISKING**: 100% liquidation of all risk assets into USDC. Transition state to `LOCKED_DOWN`. | Administrative manual override required. |

#### Automated Flight-to-USDC Execution Protocol
Upon Tier 3 trigger, severe macro breakdown ($P_{\text{BTC}} < \text{SMA}_{200} - 3\%$ and $\text{FNG} \le 20$), or contract compromise:
1. **Halt Signal Processing**: Alpha Engine signals immediately suppressed.
2. **Liquidation Priority Sequencing**: Assets liquidated in order of descending volatility to minimize aggregate market impact:
   $$\text{ARB} \to \text{USDC} \quad \longrightarrow \quad \text{LINK} \to \text{USDC} \quad \longrightarrow \quad \text{WETH} \to \text{USDC} \quad \longrightarrow \quad \text{WBTC} \to \text{USDC}$$
3. **Chunked TWAP Slicing**: If order size exceeds 2.0% of active tick liquidity, orders are sliced into 3 tranches spaced over 90 seconds.
4. **Execution Parameters**: Swaps dispatched via `SwapRouter02` with relaxed emergency slippage ceiling of 75 bps and 180s deadline to guarantee fill.

---

## 5. Modular System Architecture Specification (R4)

### 5.1 Five-Component Modular Architecture

1. **Component 1: Market Data Ingestion Subsystem (`crypto_pipeline/ingestion/`)**:
   - Collects multi-asset OHLCV candles via CCXT (Binance/Coinbase/Kraken), DeFiLlama Arbitrum TVL, and Alternative.me Fear & Greed.
   - Enforces closed-bar normalization: candle $t$ is emitted only after bar close; bar timestamp shifted strictly to $t-1$.
   - Polls Arbitrum One RPC for live block base fees and Uniswap QuoterV2 tick prices.
2. **Component 2: Quantitative Alpha Engine (`crypto_pipeline/strategies/`)**:
   - Computes continuous log-ratio $r_t$, dual EMA RMO, and rolling Z-score overextension bounds for WBTC/WETH.
   - Computes macro regime filter $\mathcal{M}_t$ and cross-sectional momentum ranking for ARB and LINK.
   - Emits unconstrained `TargetAllocationIntent`.
3. **Component 3: Risk Gating & Capital Allocation Engine (`execution/guardrails/`)**:
   - Ingests `TargetAllocationIntent`, computes normalized inverse volatility sizing, and applies Fractional Kelly budget.
   - Projects target weights onto linear concentration constraints (40% WBTC, 35% WETH, 20% alts, 10% cash).
   - Monitors dynamic Chandelier stops and 3-tier circuit breakers.
   - Dispatches orders through the existing 5-layer `PreBroadcastGuardrailPipeline` (GoPlus security, capital caps, dynamic slippage, gas check, `eth_call` simulation).
4. **Component 4: Web3.py Uniswap v3 Execution Router (`execution/routers/dex_router.py`)**:
   - Encodes `exactInputSingle` for single-hop swaps and `exactInput` packed paths for multi-hop routes (e.g. `LINK -> WETH -> USDC`).
   - Integrates Arbitrum `ArbGasInfo` for L1 blob fee estimation and EIP-1559 priority fee escalation.
   - Coordinates with `DualEngineWalletRouter` for hot keystore signing or interactive MetaMask bridge execution.
5. **Component 5: Telemetry, State Persistence & Event Logging (`visualization/`)**:
   - Persists portfolio state, positions, trade ledger, and high-water marks to SQLite.
   - Streams real-time market snapshots, alpha deliberation events, and circuit breaker status over SSE and WebSockets to the trading dashboard.

### 5.2 Interface Contracts (Pydantic V2 Schemas)

The schemas below define the authoritative type-safe contracts for inter-component communication:

```python
"""
Arbitrum Quantitative Strategy Interface Contracts (Pydantic V2).
Module: execution/contracts/quant_architecture.py
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class MacroRegime(str, Enum):
    RISK_ON = "RISK_ON"          # M_t >= 0.70: Bull trend, low vol, positive sentiment
    NEUTRAL = "NEUTRAL"          # 0.30 <= M_t < 0.70: Choppy/consolidation
    RISK_OFF = "RISK_OFF"        # M_t < 0.30: Bear trend or high volatility shock
    PANIC_DE_RISK = "PANIC_DE_RISK"  # Drawdown breaker tripped or flash crash


class CircuitBreakerStatus(str, Enum):
    NORMAL = "NORMAL"
    TIER1_CAUTION = "TIER1_CAUTION"        # Daily DD >= 3% or Cum DD >= 8%
    TIER2_DAILY_LOCK = "TIER2_DAILY_LOCK"  # Daily DD >= 5%
    TIER3_LOCKED_DOWN = "TIER3_LOCKED_DOWN"# Cum DD >= 15% (Emergency Flight to USDC)


# --- Component 1: Market State ---

class TokenMarketData(BaseModel):
    token_address: str
    symbol: str
    price_usd: float
    atr_14: float
    normalized_atr_pct: float
    volume_24h_usd: float
    fee_tier: int = 500


class MarketRegimeState(BaseModel):
    timestamp: datetime
    chain_id: int = 42161
    regime: Literal["RISK_ON", "NEUTRAL", "RISK_OFF"]
    btc_sma50_above_200: bool
    btc_realized_vol_pct: float
    fear_and_greed: int
    confidence: float = Field(ge=0.0, le=1.0)
    tokens: Dict[str, TokenMarketData]


# --- Component 2: Alpha Engine Signals ---

class AlphaSignal(BaseModel):
    pair_or_asset: str
    signal_type: Literal["RATIO_MOMENTUM", "ALTCOIN_ROTATION", "DEFENSIVE_DERISK"]
    raw_score: float
    z_score: float
    target_weight: float = Field(ge=0.0, le=1.0)
    time_horizon: str = "4h"
    look_ahead_shift_verified: bool = True


# --- Component 3: Risk Gating & Allocation ---

class RebalanceOrder(BaseModel):
    token_in: str
    token_out: str
    symbol_in: str
    symbol_out: str
    amount_in_wei: int
    amount_out_min_wei: int
    fee_tier: int
    route_path: List[str]
    estimated_slippage_bps: float
    estimated_gas_usd: float
    is_emergency_flight: bool = False


class PortfolioAllocationDecision(BaseModel):
    timestamp: datetime
    macro_regime: MacroRegime
    circuit_breaker_status: CircuitBreakerStatus
    target_weights: Dict[str, float]
    risk_budget_pct: float
    rebalance_required: bool
    orders: List[RebalanceOrder]

    @field_validator("target_weights")
    @classmethod
    def validate_weights(cls, weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Target weights must sum to 1.0 (got {total:.4f})")
        return weights


class PreBroadcastCheckResult(BaseModel):
    approved: bool
    layer_passed: Dict[str, bool]
    rejection_reason: Optional[str] = None
    simulated_gas: int = 0
    price_impact_pct: float = 0.0
```

---

## 6. Phased Implementation Roadmap & Verification Plan (R4)

### 6.1 Four-Phase Implementation Plan

```
┌────────────────────────────────────────────────────────────────────────┐
│                   PHASED IMPLEMENTATION TIMELINE                      │
├───────────────────┬───────────────────┬───────────────────┬────────────┤
│     M-Quant-1     │     M-Quant-2     │     M-Quant-3     │ M-Quant-4  │
│  Data & Pricing   │ Strategy & Signals│Risk Gate & Execute│ Simulation │
└───────────────────┴───────────────────┴───────────────────┴────────────┘
```

| Phase | Milestone Name | Scope & Concrete Deliverables | Key Test Verification Strategy | Integration Touchpoints |
|:---|:---|:---|:---|:---|
| **Phase 1** | **M-Quant-1: Data Ingestion & Microstructure Pricing** | - CCXT 4h/1d candle ingestion for WBTC, WETH, ARB, LINK.<br>- Closed-bar time-shifter ($t-1 \to t$).<br>- Arbitrum One QuoterV2 pricing client (`0x61fFE...0B21e`).<br>- Multi-hop path fee encoder. | - 100% unit tests in `tests/unit/test_quant_pricing.py`.<br>- Assert `signal.shift(1)` eliminates look-ahead bias.<br>- QuoterV2 simulation on live Arbitrum RPC. | Plugs into `crypto_pipeline/ingestion/` and `execution/routers/dex_router.py`. |
| **Phase 2** | **M-Quant-2: Quantitative Strategy & Alpha Signals** | - WBTC/WETH log-ratio & dual EMA RMO engine.<br>- Rolling Z-score overextension bounds ($Z_{\text{entry}}=1.5, Z_{\text{cap}}=2.25$).<br>- Multi-factor macro regime filter $\mathcal{M}_t$ (BTC 50/200 SMA, Vol $\le 75\%$, FNG $\ge 50$).<br>- Sortino-style altcoin momentum ranking. | - Time-series validation in `tests/unit/test_quant_strategy.py`.<br>- Walk-forward parameter stability check.<br>- Assert altcoin allocations strictly 0 when $\mathcal{M}_t < 0.30$. | Implements `crypto_pipeline/strategies/` emitting `AlphaSignal` and `TargetAllocationIntent`. |
| **Phase 3** | **M-Quant-3: Risk Gating & Uniswap v3 Execution** | - Multi-asset inverse-volatility sizer.<br>- Fractional Kelly allocator ($\lambda_{\text{Kelly}} \le 0.35$).<br>- Concentration projection (40% WBTC, 35% WETH, 20% alts, 10% cash).<br>- Dynamic Chandelier trailing stops ($2.5 - 3.0 \times \text{ATR}$).<br>- 3-tier circuit breakers with automated flight to USDC.<br>- `SwapRouter02` multi-hop calldata builder. | - Adversarial failure injection in `tests/adversarial/test_circuit_breakers.py`.<br>- Anvil Arbitrum fork execution tests in `tests/integration/test_uniswap_execution.py`.<br>- Assert zero trades exceed $\$250$ cap. | Extends `execution/guardrails/pipeline.py` and `execution/routers/dex_router.py`. |
| **Phase 4** | **M-Quant-4: End-to-End Simulation & Testnet Dry-Run** | - Event-driven historical backtester with realistic QuoterV2 slippage and gas.<br>- 180-day multi-asset simulation run.<br>- Arbitrum Sepolia live dry-run execution harness (10 consecutive testnet swaps).<br>- SSE/WebSocket telemetry streaming. | - Run `tests/e2e/test_quant_rotation_e2e.py`.<br>- Verify Sharpe Ratio $> 1.2$ and Max Drawdown $< 12\%$ in backtest.<br>- Zero reverts across 10 on-chain dry-run transactions. | Binds Components 1–5 end-to-end with visualization dashboard. |

### 6.2 Test & Quality Assurance Verification Plan

1. **Unit Test Verification**:
   - `test_log_ratio_symmetry`: Validate $\ln(P_{\text{BTC}} / P_{\text{ETH}}) = -\ln(P_{\text{ETH}} / P_{\text{BTC}})$.
   - `test_look_ahead_shift`: Verify bar $t$ signal evaluates strictly on closed bar $t-1$ data.
   - `test_inverse_vol_weights`: Verify assets with higher normalized ATR receive smaller allocations.
   - `test_concentration_clamping`: Verify no single altcoin exceeds 20.0% even when momentum score is infinite.
   - `test_dust_and_chunking`: Verify orders $<\$50$ are skipped and orders $>\$250$ are split.
2. **Integration & Adversarial Verification**:
   - `test_tier1_drawdown_halving`: Inject 3.5% daily drawdown; assert trade sizing is halved.
   - `test_tier2_daily_lockout`: Inject 5.2% daily drawdown; assert all buy orders are rejected for 24 hours.
   - `test_tier3_emergency_flight`: Inject 15.5% cumulative drawdown; assert priority sequence liquidation into 100% USDC.
   - `test_multihop_quote_fidelity`: Query live Arbitrum QuoterV2 for `LINK -> WETH -> USDC` and assert output matches expected slippage $< 20$ bps.
3. **Non-Regression Gate**:
   - Run existing suite `pytest tests/unit/test_execution.py` to confirm all 35 baseline tests continue passing without error.

---

## 7. Document Conclusion & Architectural Acceptance

This architectural specification resolves all requirements of **R1**, **R2**, **R3**, and **R4**:
1. Formulates institutional-grade mathematical models for ratio momentum, macro regime detection, and altcoin rotation without look-ahead bias.
2. Resolves critical on-chain contract addresses (Circle Native USDC `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` and QuoterV2 `0x61fFE014bA17989E743c5F6cB21bF9697530B21e`), establishes pool fee tier policies, and proves multi-hop routing superiority.
3. Defines a multi-tier risk management framework with inverse volatility sizing, Half-Kelly constraints, non-loosening Chandelier stops, and automated flight-to-USDC circuit breakers.
4. Delivers typed Pydantic V2 interface contracts and a concrete 4-phase implementation roadmap designed for seamless integration with the existing Antigravity codebase.
