"""GET /ws/stream — live fan-out of the 3 Phase-5 event types.

Payload envelope (consensus plan §5.4):

    {
        "type":     "position_update" | "decision_update" | "account_update",
        "payload":  {...service-specific dict...},
        "trace_id": "<correlation-id at publish time>",
        "ts":       "<iso-8601 UTC timestamp>",
    }

Behaviour:
  * Subscribes to the ``EventBus`` on connection accept, drains its queue
    and forwards events as JSON text frames.
  * Responds to client PING with PONG so dashboards can detect dead
    connections.
  * Cleans up (``unsubscribe_queue`` + close) on disconnect or error.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from omnitrade.application.events import (
    EVENT_ACCOUNT_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_ORCHESTRATOR_ERROR,
    EVENT_POSITION_UPDATE,
)
from omnitrade.observability.trace_context import with_context

if TYPE_CHECKING:
    from omnitrade.api.container import ApiContainer
    from omnitrade.application.events.bus import Event

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ws"])


_SUBSCRIBED_NAMES: set[str] = {
    EVENT_POSITION_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_ACCOUNT_UPDATE,
    # Phase 8.5a (plan v3 G-5): multi-agent degradation surface to the
    # frontend ConnectionBanner. Payload = {strategy, correlation_id, reason}.
    EVENT_ORCHESTRATOR_ERROR,
}


async def _ws_receive_loop(ws: WebSocket) -> None:
    """Background task — accept ping frames so disconnect surfaces promptly."""
    while True:
        msg = await ws.receive_text()
        if msg == "ping":
            await ws.send_text("pong")


def _container_from_ws(ws: WebSocket) -> ApiContainer:
    container = getattr(ws.app.state, "api_container", None)
    if container is None:
        raise RuntimeError("API container not initialised for WS endpoint")
    return container  # type: ignore[no-any-return]


@router.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    """Stream Phase-5 events to a connected dashboard client."""
    try:
        container = _container_from_ws(ws)
    except RuntimeError:
        # 1011: server is terminating the connection (internal error).
        await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    await ws.accept()
    queue = container.event_bus.subscribe_queue(_SUBSCRIBED_NAMES)

    with_context(logger).info("ws_stream.connect")
    recv_task = asyncio.create_task(_ws_receive_loop(ws))

    try:
        while True:
            send_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {send_task, recv_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if recv_task in done:
                # receive_loop only returns when the client disconnects.
                send_task.cancel()
                break
            if send_task in done:
                event: Event = send_task.result()
                envelope: dict[str, Any] = event.to_dict()
                await ws.send_json(envelope)
    except WebSocketDisconnect:
        with_context(logger).info("ws_stream.disconnect")
    except Exception as exc:  # log & exit — FastAPI closes the socket
        with_context(logger).warning("ws_stream.error", error=str(exc))
    finally:
        container.event_bus.unsubscribe_queue(queue)
        recv_task.cancel()
        try:
            await ws.close()
        except Exception as exc:  # already closed — best-effort cleanup
            with_context(logger).debug("ws_stream.close_failed", error=str(exc))


__all__ = ["router"]
