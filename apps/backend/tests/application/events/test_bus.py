"""Event bus — callback + queue fan-out + safe error handling."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omnitrade.application.events.bus import (
    EVENT_ACCOUNT_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_POSITION_UPDATE,
    Event,
    EventBus,
)


def test_event_to_dict_shape() -> None:
    e = Event(type="x", payload={"a": 1}, trace_id="t-1", ts="2026-04-18T00:00:00Z")
    assert e.to_dict() == {
        "type": "x",
        "payload": {"a": 1},
        "trace_id": "t-1",
        "ts": "2026-04-18T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_subscribe_callback_receives_payload() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe(EVENT_POSITION_UPDATE, handler)
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})

    assert received == [{"a": 1}]


@pytest.mark.asyncio
async def test_publish_without_subscribers_is_noop() -> None:
    bus = EventBus()
    await bus.publish(EVENT_DECISION_UPDATE, {"x": 1})


@pytest.mark.asyncio
async def test_subscribe_queue_receives_only_requested_events() -> None:
    bus = EventBus()
    q = bus.subscribe_queue({EVENT_DECISION_UPDATE})

    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})
    await bus.publish(EVENT_DECISION_UPDATE, {"b": 2})

    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event.type == EVENT_DECISION_UPDATE
    assert event.payload == {"b": 2}
    assert q.empty()


@pytest.mark.asyncio
async def test_subscribe_queue_default_all_events() -> None:
    bus = EventBus()
    q = bus.subscribe_queue()
    await bus.publish(EVENT_ACCOUNT_UPDATE, {"n": 1})
    await bus.publish(EVENT_DECISION_UPDATE, {"n": 2})
    await bus.publish(EVENT_POSITION_UPDATE, {"n": 3})

    types = [(await asyncio.wait_for(q.get(), timeout=1.0)).type for _ in range(3)]
    assert set(types) == {
        EVENT_ACCOUNT_UPDATE,
        EVENT_DECISION_UPDATE,
        EVENT_POSITION_UPDATE,
    }


@pytest.mark.asyncio
async def test_unsubscribe_callback_stops_delivery() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe(EVENT_POSITION_UPDATE, handler)
    bus.unsubscribe(EVENT_POSITION_UPDATE, handler)
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})

    assert received == []


@pytest.mark.asyncio
async def test_unsubscribe_queue_removes_from_fanout() -> None:
    bus = EventBus()
    q = bus.subscribe_queue({EVENT_POSITION_UPDATE})
    bus.unsubscribe_queue(q)
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})
    assert q.empty()


@pytest.mark.asyncio
async def test_queue_full_drops_event_but_does_not_raise() -> None:
    bus = EventBus(queue_maxsize=1)
    q = bus.subscribe_queue({EVENT_POSITION_UPDATE})
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})
    # 2nd should be dropped for this subscriber
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 2})
    first = await asyncio.wait_for(q.get(), timeout=1.0)
    assert first.payload == {"a": 1}
    assert q.empty()


@pytest.mark.asyncio
async def test_broken_handler_does_not_break_siblings() -> None:
    bus = EventBus()
    good: list[dict[str, Any]] = []

    async def ok(payload: dict[str, Any]) -> None:
        good.append(payload)

    async def boom(payload: dict[str, Any]) -> None:
        raise RuntimeError("nope")

    bus.subscribe(EVENT_POSITION_UPDATE, boom)
    bus.subscribe(EVENT_POSITION_UPDATE, ok)
    await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})
    assert good == [{"a": 1}]


@pytest.mark.asyncio
async def test_publish_attaches_trace_id_from_context() -> None:
    from omnitrade.observability.trace_context import correlation_id

    bus = EventBus()
    q = bus.subscribe_queue({EVENT_POSITION_UPDATE})

    token = correlation_id.set("corr-42")
    try:
        await bus.publish(EVENT_POSITION_UPDATE, {"a": 1})
    finally:
        correlation_id.reset(token)

    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event.trace_id == "corr-42"
