"""WebSocket router for live market data, indicators, order book, and guardrail telemetry."""
from __future__ import annotations

import json
import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from visualization.server.connection_manager import TelemetryConnectionManager
from visualization.server.security import check_websocket_auth

logger = logging.getLogger(__name__)
ws_router = APIRouter(tags=["Telemetry WebSocket"])

ALLOWED_CHANNELS = {"all", "ticker", "orderbook", "indicators", "guardrails", "executions"}


@ws_router.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    Full-duplex WebSocket telemetry endpoint for K-line candles,
    order book depth, technical indicators, execution markers, and guardrail state.
    """
    try:
        authorized = check_websocket_auth(websocket)
    except Exception as e:
        logger.debug("check_websocket_auth exception: %s", e)
        authorized = False

    if not authorized:
        try:
            await websocket.close(code=1008, reason="Unauthorized")
        except Exception:
            pass
        return

    manager: TelemetryConnectionManager = getattr(websocket.app.state, "ws_manager", None)
    if manager is None:
        manager = TelemetryConnectionManager()
        websocket.app.state.ws_manager = manager

    hub = getattr(websocket.app.state, "telemetry_hub", None)
    if hub is None:
        from visualization.telemetry.hub import TelemetryHub
        hub = TelemetryHub()
        websocket.app.state.telemetry_hub = hub
        hub.ws_manager = manager

    session = await manager.connect(websocket)

    # Immediately synchronize client with current cached snapshots
    try:
        if hub.latest_candle:
            await manager.send_personal({
                "channel": "websocket",
                "message_type": "ticker_update",
                "payload": hub.latest_candle.model_dump(),
            }, websocket)

        if hub.latest_orderbook:
            await manager.send_personal({
                "channel": "websocket",
                "message_type": "orderbook_snapshot",
                "payload": hub.latest_orderbook.model_dump(),
            }, websocket)

        if hub.latest_indicators:
            await manager.send_personal({
                "channel": "websocket",
                "message_type": "indicator_update",
                "payload": hub.latest_indicators.model_dump(),
            }, websocket)

        if hub.latest_guardrails:
            await manager.send_personal({
                "channel": "websocket",
                "message_type": "guardrail_state",
                "payload": hub.latest_guardrails.model_dump(),
            }, websocket)

        for ex in list(hub.recent_executions):
            await manager.send_personal({
                "channel": "websocket",
                "message_type": "execution_marker",
                "payload": ex.model_dump(),
            }, websocket)
    except Exception as e:
        logger.debug("Initial telemetry sync failed: %s", e)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type") or msg.get("message_type")

            # Heartbeat ping/pong
            if msg_type == "ping":
                await websocket.send_json({
                    "channel": "websocket",
                    "message_type": "pong",
                    "payload": {
                        "client_timestamp": msg.get("timestamp"),
                        "server_time_ms": int(time.time() * 1000),
                    },
                })
            # Channel subscription management
            elif msg_type == "subscribe":
                raw_channels = msg.get("channels", ["all"])
                channels = [c for c in raw_channels if c in ALLOWED_CHANNELS]
                await manager.subscribe(websocket, channels)
                await websocket.send_json({
                    "channel": "websocket",
                    "message_type": "subscription_ack",
                    "payload": {"status": "subscribed", "channels": channels},
                })
            elif msg_type == "unsubscribe":
                channels = msg.get("channels", [])
                await manager.unsubscribe(websocket, channels)
                await websocket.send_json({
                    "channel": "websocket",
                    "message_type": "subscription_ack",
                    "payload": {"status": "unsubscribed", "channels": channels},
                })
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.debug("WebSocket telemetry loop exception: %s", e)
        await manager.disconnect(websocket)
