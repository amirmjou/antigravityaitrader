"""
Interface Contracts and Pydantic Schemas for Antigravity Agentic Trading Platform.
Specifies exact types across Multi-Agent, Guardrails, Visualization, Remote Deliberation, and Simulation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared Ratings and Actions (M1 Multi-Agent)
# ---------------------------------------------------------------------------

class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class SentimentBand(str, Enum):
    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class ThinkingLevel(str, Enum):
    HIGH = "high"
    LOW = "low"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# Structured Agent Outputs (M1)
# ---------------------------------------------------------------------------

class ResearchPlan(BaseModel):
    recommendation: PortfolioRating = Field(
        description="The investment recommendation: Buy, Overweight, Hold, Underweight, or Sell."
    )
    rationale: str = Field(description="Summary of bull/bear debate arguments.")
    strategic_actions: str = Field(description="Concrete sizing and execution guidance.")


class TraderProposal(BaseModel):
    action: Literal["Buy", "Hold", "Sell"] = Field(
        description="Execution action: Buy, Hold, or Sell."
    )
    reasoning: str = Field(description="Technical and market justification.")
    entry_price: Optional[float] = Field(default=None, description="Absolute entry target price.")
    stop_loss: Optional[float] = Field(default=None, description="Absolute stop-loss level.")
    position_sizing: Optional[str] = Field(default=None, description="Position allocation guidance.")
    symbol: str = Field(default="BTC-USD", description="Asset symbol.")

    @field_validator("entry_price", "stop_loss", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            clean = v.strip().replace("$", "").replace(",", "")
            if clean.lower() in {"none", "n/a", "null", ""}:
                return None
            try:
                return float(clean)
            except ValueError:
                return None
        return None


class PortfolioDecision(BaseModel):
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"] = Field(
        description="Final portfolio allocation verdict."
    )
    executive_summary: str = Field(description="Concise action plan and parameters.")
    investment_thesis: str = Field(description="Evidence-based synthesis.")
    price_target: Optional[float] = Field(default=None, description="Target exit price.")
    time_horizon: Optional[str] = Field(default=None, description="Expected holding horizon.")

    @field_validator("price_target", mode="before")
    @classmethod
    def coerce_price(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            clean = v.strip().replace("$", "").replace(",", "")
            if clean.lower() in {"none", "n/a", "null", ""}:
                return None
            try:
                return float(clean)
            except ValueError:
                return None
        return None


class SentimentReport(BaseModel):
    overall_band: SentimentBand
    overall_score: float = Field(ge=0.0, le=10.0, description="Sentiment score from 0 to 10.")
    confidence: Literal["low", "medium", "high"]
    narrative: str


# ---------------------------------------------------------------------------
# Guardrail & Safety Models (M2)
# ---------------------------------------------------------------------------

class GuardrailVerdict(BaseModel):
    approved: bool = Field(description="Whether order passed all 5 pre-broadcast guardrails.")
    rejection_reason: Optional[str] = Field(default=None, description="Specific reason for rejection.")
    layer_failed: Optional[str] = Field(default=None, description="Guardrail layer that tripped.")
    simulated_gas_used: Optional[int] = Field(default=None, description="Simulated gas units.")
    quoted_amount_out_min: Optional[int] = Field(default=None, description="Minimum output tokens.")
    estimated_price_impact_pct: Optional[float] = Field(default=None, description="Calculated price impact %.")


class ChainExecutionConfig(BaseModel):
    chain_id: int
    chain_name: str
    rpc_url: str
    router_address: str
    quoter_address: Optional[str] = None
    default_slippage_bps: int = 50
    max_slippage_bps: int = 100
    gas_ceiling_gwei: float = 120.0
    gas_cost_ratio_max_pct: float = 1.5


class SwapTransactionRequest(BaseModel):
    chain_id: int
    token_in: str
    token_out: str
    amount_in_wei: int
    amount_out_min_wei: int
    recipient: str
    deadline_seconds: int = 300
    slippage_bps: int = 50
    estimated_gas_price_gwei: float = 0.1
    trade_value_usd: float = 100.0


class SwapExecutionResult(BaseModel):
    success: bool
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    gas_used: int = 0
    effective_gas_price_gwei: float = 0.0
    amount_out_wei: int = 0
    revert_reason: Optional[str] = None
    signer_mode: Literal["hot_keystore", "eip1193_metamask"] = "hot_keystore"


# ---------------------------------------------------------------------------
# Telemetry & Visualization Streaming (M3)
# ---------------------------------------------------------------------------

class AgentDeliberationEvent(BaseModel):
    event: Literal["agent_thought", "debate_turn", "tool_call", "decision", "trade_telemetry"]
    agent_role: str
    timestamp: str
    token: str
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)


class UIStreamMessage(BaseModel):
    channel: Literal["sse", "websocket"]
    message_type: str
    payload: Dict[str, Any]


class ChartCandle(BaseModel):
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    timestamp_ms: int
    bids: List[List[float]]  # [[price, size], ...]
    asks: List[List[float]]


# ---------------------------------------------------------------------------
# Crypto Deliberation & Remote Agent Models (M4)
# ---------------------------------------------------------------------------

class CryptoRecommendation(BaseModel):
    symbol: str
    rating: Literal["Buy", "Hold", "Sell"]
    bull_argument: str
    bear_argument: str
    risk_assessment: str
    position_size_usd: float
    stop_loss_pct: float
    entry_target_usd: Optional[float] = None


class ATRSizingResult(BaseModel):
    symbol: str
    portfolio_value_usd: float
    risk_pct_budget: float
    atr_14: float
    multiplier: float
    dollar_risk: float
    recommended_position_usd: float
    raw_lot_size: float
    precision_lot_size: float
    capped_by_max_notional: bool


# ---------------------------------------------------------------------------
# Jev MCP Heuristic Integration Models (R1, R3, R4)
# ---------------------------------------------------------------------------

class JevDecisionResponse(BaseModel):
    risk_verdict: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    status: str = "ok"


class JevVariantPickResponse(BaseModel):
    best_variant: Dict[str, Any]


class JevDesignReviewResponse(BaseModel):
    brand_fit: Dict[str, Any]
    visual_quality: Dict[str, Any]
    clarity: Dict[str, Any]
    cta_strength: Dict[str, Any]
    ready_to_ship: Dict[str, Any]
    next_focus: Dict[str, Any]


# ---------------------------------------------------------------------------
# Simulation & Paper Trading Models (M5)
# ---------------------------------------------------------------------------

class PaperTradingOrder(BaseModel):
    order_id: str
    symbol: str
    side: Literal["Buy", "Sell"]
    quantity: float
    price: float
    timestamp_ms: int
    status: Literal["pending", "filled", "rejected"] = "pending"


class PaperTradingPosition(BaseModel):
    symbol: str
    quantity: float
    average_entry_price: float
    current_market_price: float
    unrealized_pnl_usd: float
    realized_pnl_usd: float


class BacktestResultSummary(BaseModel):
    ticker: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    net_pnl_usd: float
    max_drawdown_pct: float
    sharpe_ratio: float
