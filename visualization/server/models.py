"""Data models and serialization contracts for visualization streaming."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

DeliberationEventType = Literal[
    "agent_thought",
    "debate_turn",
    "debate_argument",
    "tool_call",
    "proposal_generated",
    "decision",
    "trade_telemetry",
    "guardrail_status",
]


class AgentDeliberationEvent(BaseModel):
    """Structured event frame emitted over Server-Sent Events."""
    event: DeliberationEventType
    agent_role: str = Field(description="Role identifier (e.g. Bull Researcher, Trader, Market Analyst)")
    agent_name: Optional[str] = Field(default=None, description="Granular agent instance identifier")
    timestamp: str = Field(description="ISO 8601 UTC timestamp string")
    token: str = Field(description="Token chunk, full argument, or summary text")
    debate_round: Optional[int] = Field(default=None, description="Current debate round (1..max_rounds)")
    consensus_status: Optional[str] = Field(default=None, description="Consensus status: in_progress, proposed, approved, rejected")
    state_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary state snapshot or tool telemetry")
    event_id: Optional[int] = Field(default=None, description="Monotonically increasing sequence ID for reconnects")

    def to_sse_frame(self) -> str:
        """Format as strict SSE data frame."""
        lines = []
        if self.event_id is not None:
            lines.append(f"id: {self.event_id}")
        lines.append(f"event: {self.event}")
        lines.append(f"data: {self.model_dump_json()}")
        return "\n".join(lines) + "\n\n"


class UIStreamMessage(BaseModel):
    """Envelope contract for full-duplex WebSocket communication."""
    channel: Literal["sse", "websocket"] = "websocket"
    message_type: str
    payload: Dict[str, Any]


class ChartCandle(BaseModel):
    """K-line OHLCV candlestick model."""
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBookSnapshot(BaseModel):
    """Order book depth snapshot with validated sorting."""
    symbol: str
    timestamp_ms: int
    bids: List[List[float]]  # Sorted descending: [[price, size], ...]
    asks: List[List[float]]  # Sorted ascending: [[price, size], ...]
    spread: Optional[float] = None
    depth_imbalance: Optional[float] = None

    def calculate_imbalance(self) -> float:
        """Calculate order book volume imbalance: (bids_vol - asks_vol) / (bids_vol + asks_vol)."""
        bids_vol = sum(entry[1] for entry in self.bids)
        asks_vol = sum(entry[1] for entry in self.asks)
        total = bids_vol + asks_vol
        return (bids_vol - asks_vol) / total if total > 0 else 0.0


class TechnicalIndicators(BaseModel):
    """Real-time technical indicator telemetry."""
    symbol: str
    ema_20: float
    macd: float
    rsi_14: float
    atr_14: float
    adx_14: Optional[float] = None
    sma_20: Optional[float] = None
    ema_50: Optional[float] = None


class ExecutionMarker(BaseModel):
    """On-chain or simulated trade execution marker overlay."""
    type: Literal["EXECUTION_BUY", "EXECUTION_SELL"]
    price: float
    quantity: float
    tx_hash: str
    timestamp_ms: int


class GuardrailStateSnapshot(BaseModel):
    """Active pre-broadcast guardrail state telemetry."""
    approved: bool
    rejection_reason: Optional[str] = None
    layer_failed: Optional[str] = None
    simulated_gas_used: Optional[int] = None
    quoted_amount_out_min: Optional[int] = None
    estimated_price_impact_pct: Optional[float] = None
    layers: Dict[str, Any] = Field(default_factory=dict)
