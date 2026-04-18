"""DecisionService — persists AgentDecision rows and emits events."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.decision_service import DecisionService
from omnitrade.application.events import EVENT_DECISION_UPDATE, EventBus
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from tests.application._fakes import build_sqlite_session_factory


@pytest.mark.asyncio
async def test_record_persists_and_publishes() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    published: list[tuple[str, dict[str, object]]] = []

    async def _capture(payload: dict[str, object]) -> None:
        published.append((EVENT_DECISION_UPDATE, payload))

    bus.subscribe(EVENT_DECISION_UPDATE, _capture)

    service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    when = datetime(2026, 4, 18, 9, 30, tzinfo=UTC)
    dec = await service.record(
        iteration=7,
        decision_text="OPEN long BTC",
        market_analysis='{"summary":"bullish"}',
        actions_taken="[]",
        account_value=Decimal("1000"),
        positions_count=0,
        timestamp=when,
    )

    assert dec.iteration == 7
    assert dec.decision == "OPEN long BTC"
    assert dec.id is not None
    assert len(published) == 1
    _, payload = published[0]
    assert payload["iteration"] == 7
    # SQLite stores account_value as REAL so round-trip yields "1000.0"
    assert payload["account_value"].startswith("1000")


@pytest.mark.asyncio
async def test_list_recent_with_offset() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    base = datetime(2026, 4, 18, tzinfo=UTC)
    for i in range(5):
        await service.record(
            iteration=i,
            decision_text=f"d{i}",
            market_analysis="{}",
            actions_taken="[]",
            account_value=Decimal(100 + i),
            positions_count=0,
            timestamp=base.replace(minute=i),
        )

    # most recent 3 (desc by timestamp)
    first_page = await service.list_recent(limit=3)
    assert [d.iteration for d in first_page] == [4, 3, 2]

    second_page = await service.list_recent(limit=3, offset=3)
    assert [d.iteration for d in second_page] == [1, 0]
