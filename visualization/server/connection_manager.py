"""Multi-client WebSocket connection and subscription manager."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ClientSession:
    """Represents an active WebSocket client session."""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.subscriptions: Set[str] = {"all"}
        self.connected_at = time.time()
        self.last_ping = time.time()


class TelemetryConnectionManager:
    """Thread-safe WebSocket multi-client broadcast and channel subscription manager."""

    def __init__(self):
        self.sessions: Dict[WebSocket, ClientSession] = {}
        self._lock = asyncio.Lock()
        try:
            self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> ClientSession:
        """Accept WebSocket and register client session."""
        await websocket.accept()
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        cid = client_id or f"client_{len(self.sessions) + 1}_{int(time.time() * 1000)}"
        session = ClientSession(websocket, cid)
        async with self._lock:
            self.sessions[websocket] = session
        logger.debug("WebSocket client connected: %s (active: %d)", cid, len(self.sessions))
        return session

    def broadcast_sync(self, message: Dict[str, Any], channel: str = "all") -> None:
        """Thread-safe synchronous broadcast dispatch using the active running loop."""
        loop = getattr(self, "_loop", None)
        if loop is None or not loop.is_running():
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
            except RuntimeError:
                loop = None
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message, channel=channel), loop)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove and unregister client session."""
        async with self._lock:
            session = self.sessions.pop(websocket, None)
        if session:
            logger.debug("WebSocket client disconnected: %s (remaining: %d)", session.client_id, len(self.sessions))

    async def subscribe(self, websocket: WebSocket, channels: List[str]) -> None:
        """Add channel subscriptions for client."""
        async with self._lock:
            session = self.sessions.get(websocket)
            if session:
                session.subscriptions.update(channels)

    async def unsubscribe(self, websocket: WebSocket, channels: List[str]) -> None:
        """Remove channel subscriptions for client."""
        async with self._lock:
            session = self.sessions.get(websocket)
            if session:
                session.subscriptions.difference_update(channels)

    async def send_personal(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """Send message directly to a single client socket."""
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any], channel: str = "all") -> None:
        """Broadcast message to all subscribers of a channel."""
        dead_sockets: List[WebSocket] = []
        async with self._lock:
            active_sessions = list(self.sessions.items())

        for ws, session in active_sessions:
            if "all" in session.subscriptions or channel in session.subscriptions:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)

        for ws in dead_sockets:
            await self.disconnect(ws)

    def active_count(self) -> int:
        """Return number of currently connected WebSocket clients."""
        return len(self.sessions)
