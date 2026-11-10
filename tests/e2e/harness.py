"""
Unified E2E Test Harness & Progressive Integration Adapter.
Provides end-to-end execution engines across Multi-Agent, Guardrails,
Visualization, Remote Deliberation, and Paper Trading.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from tests.e2e.contracts import (
    AgentDeliberationEvent,
    ATRSizingResult,
    BacktestResultSummary,
    ChainExecutionConfig,
    CryptoRecommendation,
    GuardrailVerdict,
    PaperTradingOrder,
    PaperTradingPosition,
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    SentimentBand,
    SentimentReport,
    SwapExecutionResult,
    SwapTransactionRequest,
    ThinkingLevel,
    TraderAction,
    TraderProposal,
)
from tests.e2e.fixtures import (
    LocalJevMCPClient,
    MockCCXTExchange,
    MockGeminiAntigravityClient,
    MockGoPlusClient,
    MockPublicAPIs,
    MockRemoteAgentBridge,
    MockUniswapV3Quoter,
    MockWeb3Provider,
)


# ---------------------------------------------------------------------------
# 1. Multi-Agent Deliberation Engine (M1)
# ---------------------------------------------------------------------------

class MultiAgentDeliberationEngine:
    """Orchestrates 10-agent hierarchy, debate loops, and structured outputs."""

    def __init__(self, thinking_level: ThinkingLevel = ThinkingLevel.HIGH):
        self.thinking_level = thinking_level
        self.llm = MockGeminiAntigravityClient(thinking_level=thinking_level.value)
        self.jev = LocalJevMCPClient()
        self.max_debate_rounds = 2
        self.max_risk_discuss_rounds = 2
        self.memory_log: List[Dict[str, Any]] = []

    def run_analysts(self, symbol: str, is_crypto: bool = True) -> Dict[str, Any]:
        """Runs isolated analyst subgraphs with bounded tool loops."""
        analysts = ["Market Analyst", "Sentiment Analyst", "News Analyst"]
        if not is_crypto:
            analysts.append("Fundamentals Analyst")  # SEC filings pruned in crypto mode

        reports = {}
        for role in analysts:
            if role == "Sentiment Analyst":
                reports[role] = SentimentReport(
                    overall_band=SentimentBand.BULLISH,
                    overall_score=7.8,
                    confidence="high",
                    narrative=f"Strong on-chain accumulation and social sentiment for {symbol}.",
                )
            else:
                reports[role] = f"{role} analysis for {symbol}: Momentum indicators positive, volume expanding."
        return reports

    def run_bull_bear_debate(self, symbol: str, analyst_reports: Dict[str, Any]) -> ResearchPlan:
        """Runs multi-turn Bull vs. Bear debate synthesized by Research Manager."""
        turns = []
        for r in range(self.max_debate_rounds):
            turns.append({"speaker": "Bull Researcher", "argument": f"Turn {r+1}: Hashrate expansion and institutional adoption."})
            turns.append({"speaker": "Bear Researcher", "argument": f"Turn {r+1}: Overbought indicators and short-term resistance."})
        
        # Jev variant pick for strategy scoring
        variant_eval = self.jev.pick_variant(
            f"Consensus strategy for {symbol}",
            {"bull_thesis": "Long breakout allocation", "bear_thesis": "Wait for dip"}
        )

        plan = ResearchPlan(
            recommendation=PortfolioRating.BUY,
            rationale=f"Bull thesis carried debate with 4 turns. Jev preferred: {variant_eval['best_variant']['choice']}.",
            strategic_actions="Initiate 5% capital allocation with trailing stop-loss.",
        )
        return plan

    def run_trader_proposal(self, symbol: str, plan: ResearchPlan, market_price: float) -> TraderProposal:
        """Converts ResearchPlan into actionable TraderProposal."""
        stop_price = round(market_price * 0.97, 2)
        return TraderProposal(
            action=TraderAction.BUY.value,
            reasoning=f"Breakout alignment with ResearchPlan: {plan.rationale}",
            entry_price=market_price,
            stop_loss=stop_price,
            position_sizing="5% of portfolio",
            symbol=symbol,
        )

    def run_risk_management_debate(
        self,
        symbol: str,
        proposal: TraderProposal,
        current_drawdown: float = 0.02
    ) -> PortfolioDecision:
        """Adjudicates Aggressive, Conservative, and Neutral risk debate."""
        # Jev deterministic decision scoring
        jev_verdict = self.jev.decide(
            state={"symbol": symbol, "size": proposal.position_sizing, "drawdown": current_drawdown},
            questions={
                "risk_consensus": {
                    "type": "choice",
                    "criteria": {"APPROVE": "Safe risk profile", "REJECT": "Exceeds drawdown budget"}
                }
            }
        )

        is_approved = jev_verdict["risk_consensus"]["choice"] == "APPROVE"
        rating = PortfolioRating.BUY.value if is_approved else PortfolioRating.HOLD.value

        decision = PortfolioDecision(
            rating=rating,
            executive_summary=f"Approved position on {symbol} with risk rating {rating}.",
            investment_thesis=f"Risk debaters reached consensus. Jev heuristic score: {jev_verdict['risk_consensus']['confidence']}.",
            price_target=round((proposal.entry_price or 100.0) * 1.10, 2),
            time_horizon="1-2 weeks",
        )
        # Settle to memory log
        self.memory_log.append({
            "symbol": symbol,
            "decision": decision.model_dump(),
            "timestamp": int(time.time()),
        })
        return decision


# ---------------------------------------------------------------------------
# 2. Pre-Broadcast Safety Guardrail Pipeline (M2)
# ---------------------------------------------------------------------------

class PreBroadcastGuardrailPipeline:
    """
    5-layer pre-broadcast safety pipeline:
    Layer 1: GoPlus Contract Security & Honeypot Check
    Layer 2: Capital Allocation & Drawdown Caps
    Layer 3: Uniswap v3 IQuoterV2 Slippage & Price Impact
    Layer 4: Gas Ceiling & Gas-to-Trade Ratio
    Layer 5: eth_call Dry-Run Pre-Flight Simulation
    """

    def __init__(
        self,
        chain_config: ChainExecutionConfig,
        web3_provider: MockWeb3Provider,
        goplus_client: MockGoPlusClient,
        quoter: MockUniswapV3Quoter,
        max_spend_per_trade_usd: float = 250.0,
        max_asset_concentration_pct: float = 20.0,
        max_daily_drawdown_pct: float = 8.0,
    ):
        self.config = chain_config
        self.w3 = web3_provider
        self.goplus = goplus_client
        self.quoter = quoter
        self.max_spend_per_trade_usd = max_spend_per_trade_usd
        self.max_asset_concentration_pct = max_asset_concentration_pct
        self.max_daily_drawdown_pct = max_daily_drawdown_pct

    def evaluate(
        self,
        request: SwapTransactionRequest,
        current_portfolio_value_usd: float = 5000.0,
        current_asset_holdings_usd: float = 400.0,
        current_daily_drawdown_pct: float = 2.0,
        override_quoter_impact_pct: Optional[float] = None,
    ) -> GuardrailVerdict:
        # Layer 1: Contract Security (GoPlus)
        if request.token_in.lower() == request.token_out.lower():
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 1: Self-swap rejected - token_in and token_out cannot be the same asset",
                layer_failed="Layer 1: Contract Security",
            )

        if request.amount_in_wei <= 0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 1: Non-positive amount_in_wei rejected - amount must be > 0",
                layer_failed="Layer 1: Contract Security",
            )

        sec_in = self.goplus.check_token_security(request.chain_id, request.token_in)
        sec_out = self.goplus.check_token_security(request.chain_id, request.token_out)

        for sec, name in [(sec_in, "token_in"), (sec_out, "token_out")]:
            if sec.get("is_honeypot") == "1":
                return GuardrailVerdict(
                    approved=False,
                    rejection_reason=f"Layer 1 Honeypot detected on {name}.",
                    layer_failed="Layer 1: Contract Security",
                )
            buy_tax = float(sec.get("buy_tax", "0.0"))
            sell_tax = float(sec.get("sell_tax", "0.0"))
            if buy_tax > 0.01 or sell_tax > 0.01:
                return GuardrailVerdict(
                    approved=False,
                    rejection_reason=f"Layer 1 Tax exceeds 1% ceiling (buy: {buy_tax*100}%, sell: {sell_tax*100}%).",
                    layer_failed="Layer 1: Contract Security",
                )

        # Layer 2: Capital Allocation & Drawdown
        if request.trade_value_usd <= 0.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 2: Non-positive trade_value_usd rejected - trade value must be > $0.00",
                layer_failed="Layer 2: Capital Allocation",
            )

        if current_portfolio_value_usd <= 0.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 2: Non-positive portfolio value rejected - current portfolio value must be > $0.00",
                layer_failed="Layer 2: Capital Allocation",
            )

        if request.trade_value_usd > self.max_spend_per_trade_usd:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Per-trade spend ${request.trade_value_usd} exceeds cap of ${self.max_spend_per_trade_usd}.",
                layer_failed="Layer 2: Capital Allocation",
            )
        
        new_asset_total = current_asset_holdings_usd + request.trade_value_usd
        concentration_pct = (new_asset_total / current_portfolio_value_usd) * 100.0 if current_portfolio_value_usd > 0 else 100.0
        if concentration_pct > self.max_asset_concentration_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Asset concentration {concentration_pct:.1f}% exceeds max {self.max_asset_concentration_pct}%.",
                layer_failed="Layer 2: Capital Allocation",
            )

        if current_daily_drawdown_pct >= self.max_daily_drawdown_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 2 Daily drawdown {current_daily_drawdown_pct:.1f}% exceeds circuit breaker {self.max_daily_drawdown_pct}%.",
                layer_failed="Layer 2: Capital Allocation",
            )

        # Layer 3: Dynamic Slippage & Price Impact
        if request.slippage_bps < 0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 3: Negative slippage tolerance rejected",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.slippage_bps > self.config.max_slippage_bps:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Requested slippage {request.slippage_bps} bps exceeds max {self.config.max_slippage_bps} bps.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        amount_out_wei, price_impact_pct, _ = self.quoter.quote_exact_input_single(
            request.token_in, request.token_out, request.amount_in_wei
        )
        if override_quoter_impact_pct is not None:
            price_impact_pct = override_quoter_impact_pct

        if price_impact_pct > 2.0:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Price impact {price_impact_pct:.2f}% exceeds 2.0% threshold.",
                layer_failed="Layer 3: Dynamic Slippage",
                estimated_price_impact_pct=price_impact_pct,
            )

        if request.deadline_seconds < 1:
            return GuardrailVerdict(
                approved=False,
                rejection_reason="Layer 3: Non-positive deadline rejected",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        if request.deadline_seconds > 300:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 3 Transaction deadline {request.deadline_seconds}s exceeds 300s limit.",
                layer_failed="Layer 3: Dynamic Slippage",
            )

        # Layer 4: Gas & Congestion
        if self.w3.base_fee_gwei > self.config.gas_ceiling_gwei:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 4 Network base fee {self.w3.base_fee_gwei} gwei exceeds ceiling {self.config.gas_ceiling_gwei} gwei.",
                layer_failed="Layer 4: Gas & Congestion",
            )

        simulated_gas = 145000
        # Calculate gas cost in USD assuming ETH = $3100
        gas_cost_usd = (simulated_gas * (self.w3.base_fee_gwei + self.w3.priority_fee_gwei) * 1e-9) * 3100.0
        gas_ratio_pct = (gas_cost_usd / request.trade_value_usd) * 100.0 if request.trade_value_usd > 0 else float('inf')
        if gas_ratio_pct > self.config.gas_cost_ratio_max_pct:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 4 Gas-to-trade ratio {gas_ratio_pct:.2f}% exceeds max {self.config.gas_cost_ratio_max_pct}%.",
                layer_failed="Layer 4: Gas & Congestion",
            )

        # Layer 5: eth_call Dry-Run Pre-Flight Simulation
        try:
            self.w3.eth_call({
                "to": self.config.router_address,
                "amount_in": request.amount_in_wei,
                "amount_out_min": request.amount_out_min_wei,
            })
        except Exception as e:
            return GuardrailVerdict(
                approved=False,
                rejection_reason=f"Layer 5 Simulation reverted: {str(e)}",
                layer_failed="Layer 5: Pre-Flight Simulation",
            )

        # Passed all 5 layers
        return GuardrailVerdict(
            approved=True,
            simulated_gas_used=simulated_gas,
            quoted_amount_out_min=amount_out_wei,
            estimated_price_impact_pct=price_impact_pct,
        )


# ---------------------------------------------------------------------------
# 3. Dual-Engine Wallet & DEX Router (M2)
# ---------------------------------------------------------------------------

class DualEngineWalletRouter:
    """Manages hot-wallet keystore signing and interactive MetaMask bridge."""

    def __init__(self, web3_provider: MockWeb3Provider, chain_config: ChainExecutionConfig):
        self.w3 = web3_provider
        self.config = chain_config

    def execute_swap(
        self,
        request: SwapTransactionRequest,
        signer_mode: str = "hot_keystore"
    ) -> SwapExecutionResult:
        """Signs and broadcasts swap transaction."""
        raw_tx = f"0xRAW_SIGNED_TX_CHAIN_{self.config.chain_id}_{signer_mode}_{request.amount_in_wei}"
        try:
            tx_hash = self.w3.send_raw_transaction(raw_tx)
            return SwapExecutionResult(
                success=True,
                tx_hash=tx_hash,
                block_number=self.w3.get_block_number(),
                gas_used=145000,
                effective_gas_price_gwei=self.w3.base_fee_gwei,
                amount_out_wei=request.amount_out_min_wei,
                signer_mode=signer_mode,  # type: ignore
            )
        except Exception as e:
            return SwapExecutionResult(
                success=False,
                revert_reason=str(e),
                signer_mode=signer_mode,  # type: ignore
            )


# ---------------------------------------------------------------------------
# 4. Visualization & Telemetry Streaming Hub (M3)
# ---------------------------------------------------------------------------

class VisualizationStreamHub:
    """Publishes SSE deliberation events and WebSocket telemetry."""

    def __init__(self):
        self.sse_subscribers: List[str] = []
        self.event_stream: List[AgentDeliberationEvent] = []
        self.ws_telemetry: List[Dict[str, Any]] = []
        self.jev = LocalJevMCPClient()

    def publish_event(self, event_type: str, role: str, token: str, snapshot: Optional[Dict[str, Any]] = None):
        ev = AgentDeliberationEvent(
            event=event_type,  # type: ignore
            agent_role=role,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            token=token,
            state_snapshot=snapshot or {},
        )
        self.event_stream.append(ev)

    def review_ui_design(self, brief: str, summary: str):
        """Quality gates UI using Jev review design."""
        return self.jev.review_design(brief, summary)


# ---------------------------------------------------------------------------
# 5. Crypto Ingestion & Sizing Engine (M4)
# ---------------------------------------------------------------------------

class CryptoIngestionSizingEngine:
    """Handles CCXT market data, ATR-14 sizing, and remote agent bridge."""

    def __init__(self, exchange: Optional[MockCCXTExchange] = None):
        self.exchange = exchange or MockCCXTExchange("binance")
        self.remote_bridge = MockRemoteAgentBridge()

    def calculate_atr14_sizing(
        self,
        symbol: str,
        portfolio_value_usd: float = 10000.0,
        risk_pct_budget: float = 0.01,  # 1% account risk
        multiplier: float = 1.5,
        max_notional_cap_usd: float = 250.0,
    ) -> ATRSizingResult:
        """Calculates volatility-adjusted position size based on ATR-14."""
        candles = self.exchange.fetch_ohlcv(symbol, timeframe="1h", limit=14)
        tr_list = []
        for i in range(1, len(candles)):
            high = candles[i][2]
            low = candles[i][3]
            prev_close = candles[i - 1][4]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        atr_14 = sum(tr_list) / len(tr_list) if tr_list else 100.0
        
        dollar_risk = portfolio_value_usd * risk_pct_budget
        price = candles[-1][4]
        stop_distance = atr_14 * multiplier
        raw_position_size = dollar_risk / stop_distance
        recommended_position_usd = raw_position_size * price

        capped = False
        if recommended_position_usd > max_notional_cap_usd:
            recommended_position_usd = max_notional_cap_usd
            raw_position_size = recommended_position_usd / price
            capped = True

        precision_str = self.exchange.amount_to_precision(symbol, raw_position_size)
        precision_lot = float(precision_str)

        return ATRSizingResult(
            symbol=symbol,
            portfolio_value_usd=portfolio_value_usd,
            risk_pct_budget=risk_pct_budget,
            atr_14=atr_14,
            multiplier=multiplier,
            dollar_risk=dollar_risk,
            recommended_position_usd=recommended_position_usd,
            raw_lot_size=raw_position_size,
            precision_lot_size=precision_lot,
            capped_by_max_notional=capped,
        )

    def execute_remote_agent(self, symbol: str) -> CryptoRecommendation:
        """Calls agy --remote-agent and parses recommendation."""
        code, stdout, stderr = self.remote_bridge.run_remote_deliberation(
            symbol, f"Deliberate on spot trading strategy for {symbol}"
        )
        if code != 0:
            raise RuntimeError(f"Remote agent failed: {stderr}")
        data = json.loads(stdout)["response"]
        return CryptoRecommendation(**data)


# ---------------------------------------------------------------------------
# 6. Paper Trading & Simulation Engine (M5)
# ---------------------------------------------------------------------------

class PaperTradingEngine:
    """Simulated exchange order matching and portfolio book."""

    def __init__(self, initial_cash_usd: float = 10000.0):
        self.cash_usd = initial_cash_usd
        self.positions: Dict[str, PaperTradingPosition] = {}
        self.orders: List[PaperTradingOrder] = []

    def place_order(self, symbol: str, side: str, quantity: float, price: float) -> PaperTradingOrder:
        order_cost = quantity * price
        order = PaperTradingOrder(
            order_id=f"order_{len(self.orders)+1}",
            symbol=symbol,
            side=side,  # type: ignore
            quantity=quantity,
            price=price,
            timestamp_ms=int(time.time() * 1000),
            status="pending",
        )
        if quantity <= 0 or price <= 0:
            order.status = "rejected"
            self.orders.append(order)
            return order
        if side == "Buy":
            if order_cost > self.cash_usd:
                order.status = "rejected"
            else:
                self.cash_usd -= order_cost
                order.status = "filled"
                pos = self.positions.get(symbol)
                if not pos:
                    self.positions[symbol] = PaperTradingPosition(
                        symbol=symbol,
                        quantity=quantity,
                        average_entry_price=price,
                        current_market_price=price,
                        unrealized_pnl_usd=0.0,
                        realized_pnl_usd=0.0,
                    )
                else:
                    new_qty = pos.quantity + quantity
                    pos.average_entry_price = ((pos.quantity * pos.average_entry_price) + order_cost) / new_qty
                    pos.quantity = new_qty
        elif side == "Sell":
            pos = self.positions.get(symbol)
            if not pos or pos.quantity < quantity:
                order.status = "rejected"
            else:
                pos.quantity -= quantity
                self.cash_usd += order_cost
                order.status = "filled"
        self.orders.append(order)
        return order
