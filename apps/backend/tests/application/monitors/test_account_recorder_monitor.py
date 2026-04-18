"""AccountRecorderMonitor — cadence + passthrough to AccountService."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.account_service import AccountService
from omnitrade.application.events import EventBus
from omnitrade.application.monitors.account_recorder_monitor import AccountRecorderMonitor
from omnitrade.domain.entities import AccountSnapshot
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from tests.application._fakes import FakeClock, FakeExchange, build_sqlite_session_factory


def _snap(total: Decimal) -> AccountSnapshot:
    return AccountSnapshot(
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        total_value=total,
        available_cash=total,
        unrealized_pnl=Decimal(0),
        realized_pnl=Decimal(0),
        return_percent=Decimal(0),
    )


@pytest.mark.asyncio
async def test_tick_records_snapshot_via_service() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    ex = FakeExchange(balance=_snap(Decimal("777")), positions=[])
    svc = AccountService(
        exchange=ex,
        history_repo=AccountHistoryRepository(),
        position_repo=PositionRepository(),
        session_factory=open_session,
        event_bus=bus,
        initial_balance=Decimal("1000"),
    )
    mon = AccountRecorderMonitor(
        interval_minutes=1,
        account_service=svc,
        clock=FakeClock(),
    )
    assert mon.interval_seconds == 60.0

    await mon.tick()

    session = await open_session()
    try:
        rows = await AccountHistoryRepository().list_recent(session)
    finally:
        await session.close()
    assert len(rows) == 1
    assert rows[0].total_value == Decimal("777")
