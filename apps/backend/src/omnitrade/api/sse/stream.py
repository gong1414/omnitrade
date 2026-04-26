"""GET /sse/stream — Server-Sent Events fan-out of the dashboard event types.

Same envelope as the WebSocket stream at ``api/ws/stream.py`` — the SSE
endpoint exists so Stage C of the Agno cutover can flip the dashboard's
realtime transport (`apps/frontend/lib/sse/client.ts`) without backend
regression. Subscribes to the same ``EventBus`` and emits one SSE
``message`` per published event.

Each event is sent on a named SSE channel matching its ``type`` so
``EventSource.addEventListener("decision_update", ...)`` works in the
browser. The default ``onmessage`` channel also receives the full
envelope, mirroring the WS shape for clients that don't care about
named events.

Envelope::

    {
        "type":     "position_update" | "decision_update" |
                    "account_update" | "orchestrator_error",
        "payload":  {...service-specific dict...},
        "trace_id": "<correlation-id at publish time>",
        "ts":       "<iso-8601 UTC timestamp>",
    }
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from omnitrade.application.events import (
    EVENT_ACCOUNT_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_ORCHESTRATOR_ERROR,
    EVENT_POSITION_UPDATE,
)
from omnitrade.observability.trace_context import with_context

if TYPE_CHECKING:
    from omnitrade.api.container import ApiContainer

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["sse"])


_SUBSCRIBED_NAMES: set[str] = {
    EVENT_POSITION_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_ACCOUNT_UPDATE,
    EVENT_ORCHESTRATOR_ERROR,
}

# Heartbeat interval — keeps middleboxes from culling the long-lived
# connection during quiet periods (no events between cycles). 15s matches
# typical proxy idle timeouts.
_HEARTBEAT_SECONDS: float = 15.0


def _format_sse(event_type: str, payload: dict) -> bytes:
    """Render one SSE message frame (`event:` + `data:` + blank line)."""
    body = json.dumps(payload, default=str)
    return f"event: {event_type}\ndata: {body}\n\n".encode()


@router.get("/sse/stream")
async def sse_stream(request: Request) -> StreamingResponse:
    """Stream dashboard events to a connected SSE client."""
    container: ApiContainer | None = getattr(request.app.state, "api_container", None)
    if container is None:
        # SSE clients can't see HTTP status detail mid-stream; refuse upfront.
        return StreamingResponse(
            iter([_format_sse("error", {"message": "container not initialised"})]),
            media_type="text/event-stream",
            status_code=503,
        )

    queue = container.event_bus.subscribe_queue(_SUBSCRIBED_NAMES)
    with_context(logger).info("sse_stream.connect")

    async def _event_generator() -> AsyncGenerator[bytes, None]:
        # Initial comment frame helps EventSource flush headers immediately.
        yield b": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield b": ping\n\n"
                    continue
                envelope = event.to_dict()
                yield _format_sse(envelope.get("type", "message"), envelope)
        except asyncio.CancelledError:  # client disconnected mid-await
            with_context(logger).info("sse_stream.cancelled")
            raise
        except Exception as exc:  # log + exit cleanly
            with_context(logger).warning("sse_stream.error", error=str(exc))
        finally:
            container.event_bus.unsubscribe_queue(queue)
            with_context(logger).info("sse_stream.disconnect")

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            # Defeat any reverse-proxy buffering; SSE wants chunks delivered
            # immediately, not waited on a flush threshold.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


__all__ = ["router"]
