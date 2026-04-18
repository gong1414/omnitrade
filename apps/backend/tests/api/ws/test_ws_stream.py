"""WS /ws/stream — fan-out of the 3 Phase-5 event types."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient

from omnitrade.application.events import (
    EVENT_ACCOUNT_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_POSITION_UPDATE,
)


@pytest.mark.asyncio
async def test_ws_stream_receives_three_event_types(api_app) -> None:  # type: ignore[no-untyped-def]
    """Publish one of each event type and confirm the WS client receives all three."""
    # Starlette's TestClient is sync under the hood but supports websocket_connect.
    with TestClient(api_app) as client:
        with client.websocket_connect("/ws/stream") as ws:
            bus = api_app.state.api_container.event_bus
            await bus.publish(EVENT_POSITION_UPDATE, {"action": "open", "symbol": "BTC_USDT"})
            await bus.publish(EVENT_DECISION_UPDATE, {"iteration": 1, "action": "hold"})
            await bus.publish(
                EVENT_ACCOUNT_UPDATE,
                {"total_value": str(Decimal("1000"))},
            )

            types: list[str] = []
            for _ in range(3):
                event = ws.receive_json()
                types.append(event["type"])
                assert "payload" in event
                assert "trace_id" in event
                assert "ts" in event

            assert set(types) == {
                EVENT_POSITION_UPDATE,
                EVENT_DECISION_UPDATE,
                EVENT_ACCOUNT_UPDATE,
            }


# Use a plain fixture for ASGITransport default (satisfies import linter).
_ = ASGITransport
