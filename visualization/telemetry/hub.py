"""Central Telemetry Hub and historical ring buffer for SSE and WebSocket telemetry."""
from __future__ import annotations

import asyncio
from collections import deque
import threading
import time
from typing import Any, Dict, List, Optional

from core.agents.jev_adapter import JevAdapter
from visualization.server.models import (
    AgentDeliberationEvent,
    ChartCandle,
    ExecutionMarker,
    GuardrailStateSnapshot,
    OrderBookSnapshot,
    TechnicalIndicators,
)


class TelemetryHub:
    """Thread-safe central publishing hub and 2,000-event ring buffer."""

    def __init__(self, max_event_backlog: int = 2000, jev_client: Optional[Any] = None):
        self.max_event_backlog = max_event_backlog
        self.event_backlog: deque[AgentDeliberationEvent] = deque(maxlen=max_event_backlog)
        self.event_sequence: int = 0
        self.sse_subscribers: List[asyncio.Queue] = []
        self._thread_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self.jev = jev_client or JevAdapter()

        # Telemetry state caches
        self.latest_candle: Optional[ChartCandle] = None
        self.latest_orderbook: Optional[OrderBookSnapshot] = None
        self.latest_indicators: Optional[TechnicalIndicators] = None
        self.latest_guardrails: Optional[GuardrailStateSnapshot] = None
        self.recent_executions: deque[ExecutionMarker] = deque(maxlen=50)

        # Injected reference to WebSocket manager
        self.ws_manager = None

    @property
    def event_stream(self) -> List[AgentDeliberationEvent]:
        """Backward-compatible property returning list of all events in buffer."""
        with self._thread_lock:
            return list(self.event_backlog)

    def publish_event(
        self,
        event_type: str,
        role: str,
        token: str,
        snapshot: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None,
        debate_round: Optional[int] = None,
        consensus_status: Optional[str] = None,
    ) -> AgentDeliberationEvent:
        """Publishes an event thread-safely into ring buffer and dispatches to listeners."""
        with self._thread_lock:
            self.event_sequence += 1
            ev = AgentDeliberationEvent(
                event=event_type,  # type: ignore
                agent_role=role,
                agent_name=agent_name or role,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                token=token,
                debate_round=debate_round,
                consensus_status=consensus_status,
                state_snapshot=snapshot or {},
                event_id=self.event_sequence,
            )
            self.event_backlog.append(ev)
            current_subscribers = list(self.sse_subscribers)

        # Fan-out to async SSE subscriber queues
        for q in current_subscribers:
            try:
                q.put_nowait(ev)
            except Exception:
                pass

        if event_type in {"trade_telemetry", "guardrail_status"}:
            self._dispatch_ws(event_type, ev.model_dump())

        return ev

    def _dispatch_ws(self, message_type: str, payload: Dict[str, Any], channel: str = "all") -> None:
        if self.ws_manager is None:
            return
        msg = {
            "channel": "websocket",
            "message_type": message_type,
            "payload": payload,
        }
        if hasattr(self.ws_manager, "broadcast_sync"):
            self.ws_manager.broadcast_sync(msg, channel=channel)
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.ws_manager.broadcast(msg, channel=channel))
            except RuntimeError:
                pass

    def update_candle(self, candle: ChartCandle | Dict[str, Any]) -> ChartCandle:
        """Update the latest candle and broadcast over WebSocket if manager active."""
        if isinstance(candle, dict):
            c = ChartCandle(**candle)
        else:
            c = candle
        self.latest_candle = c
        self._dispatch_ws("ticker_update", c.model_dump())
        return c

    def update_orderbook(self, orderbook: OrderBookSnapshot | Dict[str, Any]) -> OrderBookSnapshot:
        """Update the latest order book depth snapshot and broadcast over WebSocket."""
        if isinstance(orderbook, dict):
            ob = OrderBookSnapshot(**orderbook)
        else:
            ob = orderbook
        if ob.depth_imbalance is None:
            ob.depth_imbalance = ob.calculate_imbalance()
        if ob.spread is None and ob.bids and ob.asks:
            ob.spread = round(ob.asks[0][0] - ob.bids[0][0], 2)
        self.latest_orderbook = ob
        self._dispatch_ws("orderbook_snapshot", ob.model_dump())
        return ob

    def update_indicators(self, indicators: TechnicalIndicators | Dict[str, Any]) -> TechnicalIndicators:
        """Update technical indicators."""
        if isinstance(indicators, dict):
            ind = TechnicalIndicators(**indicators)
        else:
            ind = indicators
        self.latest_indicators = ind
        self._dispatch_ws("indicator_update", ind.model_dump())
        return ind

    def record_execution(self, marker: ExecutionMarker | Dict[str, Any]) -> ExecutionMarker:
        """Record trade execution marker and broadcast."""
        if isinstance(marker, dict):
            m = ExecutionMarker(**marker)
        else:
            m = marker
        self.recent_executions.append(m)
        self._dispatch_ws("execution_marker", m.model_dump())
        return m

    def update_guardrails(self, snapshot: GuardrailStateSnapshot | Dict[str, Any]) -> GuardrailStateSnapshot:
        """Update guardrail shield state and broadcast."""
        if isinstance(snapshot, dict):
            gs = GuardrailStateSnapshot(**snapshot)
        else:
            gs = snapshot
        self.latest_guardrails = gs
        self._dispatch_ws("guardrail_state", gs.model_dump())
        return gs

    async def subscribe_sse(self, since_id: Optional[int] = None) -> asyncio.Queue:
        """Register a new SSE client queue, replaying backlog atomically before live events."""
        q: asyncio.Queue = asyncio.Queue()
        async with self._async_lock:
            with self._thread_lock:
                if since_id is not None:
                    for ev in self.event_backlog:
                        if ev.event_id is not None and ev.event_id > since_id:
                            q.put_nowait(ev)
                self.sse_subscribers.append(q)
        return q

    async def unsubscribe_sse(self, q: asyncio.Queue) -> None:
        """Unregister an SSE client queue."""
        async with self._async_lock:
            with self._thread_lock:
                if q in self.sse_subscribers:
                    self.sse_subscribers.remove(q)

    def review_ui_design(self, brief: str, summary: str) -> Dict[str, Any]:
        """Quality gates UI using Jev review design."""
        return self.jev.review_design(brief, summary)


# Alias for 100% compatibility with test harness
VisualizationStreamHub = TelemetryHub
