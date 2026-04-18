"""EventBus — pub/sub for application events (positions, decisions, account).

Implements the ``omnitrade.domain.protocols.EventBus`` contract with a small
in-process fan-out: every subscriber owns an ``asyncio.Queue`` that receives
a copy of each published ``Event``. WS subscribers drain their queue;
callback subscribers are invoked directly (fire-and-forget with error logging).

Every envelope carries ``trace_id`` (from ``get_correlation_id()`` at publish
time) and an ISO-8601 UTC timestamp so dashboard clients can stitch logs
across services.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from omnitrade.observability.trace_context import get_correlation_id, with_context

logger = structlog.get_logger(__name__)


# Canonical event names broadcast on the bus.
EVENT_POSITION_UPDATE = "position_update"
EVENT_DECISION_UPDATE = "decision_update"
EVENT_ACCOUNT_UPDATE = "account_update"
# Phase 8.5a (plan v3 G-5): multi-agent orchestrator degradation surface
# — payload carries {strategy, correlation_id, reason}.
EVENT_ORCHESTRATOR_ERROR = "orchestrator_error"


@dataclass(frozen=True)
class Event:
    """Envelope delivered to every subscriber.

    Shape matches the WS payload documented in the Phase 5.4 contract:
    ``{"type", "payload", "trace_id", "ts"}``.
    """

    type: str
    payload: dict[str, Any]
    trace_id: str = ""
    ts: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "trace_id": self.trace_id,
            "ts": self.ts,
        }


AsyncHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process async event bus.

    Two subscriber flavours:
      * ``subscribe(name, handler)`` — callback fired per publish.
      * ``subscribe_queue(names)`` — returns an ``asyncio.Queue`` that
        receives events for every name in ``names``; WS handlers use this
        so they can await events and forward them downstream.
    """

    def __init__(self, queue_maxsize: int = 128) -> None:
        self._handlers: dict[str, list[AsyncHandler]] = {}
        self._queues: list[tuple[set[str], asyncio.Queue[Event]]] = []
        self._queue_maxsize = queue_maxsize

    # ── callback-style subscription (EventBusProtocol) ────────────────── #

    def subscribe(self, event_name: str, handler: AsyncHandler) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def unsubscribe(self, event_name: str, handler: AsyncHandler) -> None:
        bucket = self._handlers.get(event_name)
        if not bucket:
            return
        try:
            bucket.remove(handler)
        except ValueError:
            pass

    # ── queue-style subscription (WS) ─────────────────────────────────── #

    def subscribe_queue(
        self,
        event_names: set[str] | None = None,
    ) -> asyncio.Queue[Event]:
        """Return a fresh queue receiving events for the given names.

        ``event_names=None`` subscribes to every event.
        """
        names: set[str] = (
            set(event_names)
            if event_names is not None
            else {
                EVENT_POSITION_UPDATE,
                EVENT_DECISION_UPDATE,
                EVENT_ACCOUNT_UPDATE,
                EVENT_ORCHESTRATOR_ERROR,
            }
        )
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues.append((names, queue))
        return queue

    def unsubscribe_queue(self, queue: asyncio.Queue[Event]) -> None:
        self._queues = [(names, q) for names, q in self._queues if q is not queue]

    # ── publish ───────────────────────────────────────────────────────── #

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        """Broadcast a new event to every matching subscriber.

        Callbacks run concurrently; exceptions are logged and swallowed so
        one broken subscriber cannot stop the fan-out. Queue subscribers
        receive the event synchronously — if their queue is full the event
        is dropped for that subscriber (with a warning).
        """
        event = Event(
            type=event_name,
            payload=payload,
            trace_id=get_correlation_id(),
        )
        with_context(logger).info("event_bus.publish", event_type=event_name)

        # Queue subscribers first (non-blocking put_nowait).
        for names, queue in self._queues:
            if event_name in names:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    with_context(logger).warning(
                        "event_bus.queue_full_drop",
                        event_type=event_name,
                    )

        # Callback subscribers.
        handlers = list(self._handlers.get(event_name, []))
        if not handlers:
            return
        await asyncio.gather(
            *(self._safe_call(h, event_name, payload) for h in handlers),
            return_exceptions=True,
        )

    async def _safe_call(
        self,
        handler: AsyncHandler,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await handler(payload)
        except Exception as exc:  # log-and-continue pattern
            with_context(logger).error(
                "event_bus.handler_error",
                event_type=event_name,
                error=str(exc),
            )


__all__ = [
    "EVENT_ACCOUNT_UPDATE",
    "EVENT_DECISION_UPDATE",
    "EVENT_ORCHESTRATOR_ERROR",
    "EVENT_POSITION_UPDATE",
    "AsyncHandler",
    "Event",
    "EventBus",
]
