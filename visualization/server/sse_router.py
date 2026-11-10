"""Server-Sent Events (SSE) router for multi-agent reasoning and deliberation streaming."""
from __future__ import annotations

import asyncio
import os
import time
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, Header, Query, Request
from starlette.responses import StreamingResponse

from visualization.server.models import AgentDeliberationEvent
from visualization.server.security import get_allowed_origins, is_production_mode, verify_api_token

sse_router = APIRouter(tags=["Reasoning SSE Stream"])


async def sse_event_generator(
    request: Request,
    since_id: Optional[int],
    hub,
    limit: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Yields SSE frames with 15-second keepalive heartbeats and backlog replay."""
    queue = await hub.subscribe_sse(since_id=since_id)
    last_ping = time.time()
    try:
        yield ": connected\n\n"
        count = 1
        while True:
            if limit is not None and count >= limit:
                break
            try:
                event: AgentDeliberationEvent = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event.to_sse_frame()
                count += 1
                last_ping = time.time()
                if limit is not None and count >= limit:
                    break
            except asyncio.TimeoutError:
                if time.time() - last_ping >= 15.0:
                    yield ": keepalive\n\n"
                    last_ping = time.time()
    except asyncio.CancelledError:
        pass
    finally:
        await hub.unsubscribe_sse(queue)


@sse_router.get("/events/reasoning")
@sse_router.get("/api/deliberation/stream")
async def stream_reasoning(
    request: Request,
    since_id: Optional[int] = Query(None, description="Event sequence ID to replay from"),
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    limit: Optional[int] = Query(None, description="Optional maximum number of events to yield before closing"),
    _token: str = Depends(verify_api_token),
):
    """
    Server-Sent Events endpoint streaming real-time agent reasoning tokens,
    debate arguments, tool calls, proposals, and decisions.
    Supports dual routes: /events/reasoning and /api/deliberation/stream.
    """
    effective_since = since_id if since_id is not None else last_event_id
    hub = getattr(request.app.state, "telemetry_hub", None)
    if hub is None:
        from visualization.telemetry.hub import TelemetryHub
        hub = TelemetryHub()
        request.app.state.telemetry_hub = hub

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    req_origin = request.headers.get("origin")
    allowed = get_allowed_origins()
    if req_origin and req_origin in allowed:
        headers["Access-Control-Allow-Origin"] = req_origin
        headers["Access-Control-Allow-Credentials"] = "true"
    elif not is_production_mode() and not os.environ.get("ALLOWED_ORIGINS"):
        headers["Access-Control-Allow-Origin"] = "*"

    return StreamingResponse(
        sse_event_generator(request, effective_since, hub, limit=limit),
        media_type="text/event-stream",
        headers=headers,
    )
