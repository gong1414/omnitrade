"""AccountService — snapshot persistence + peak/drawdown + events."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.account_service import AccountService
from omnitrade.application.events import EVENT_ACCOUNT_UPDATE, EventBus
from omnitrade.domain.entities import AccountSnapshot
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from tests.application._fakes import FakeExchange, build_sqlite_session_factory


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
async def test_record_snapshot_persists_and_publishes() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    published: list[dict[str, object]] = []

    async def _capture(payload: dict[str, object]) -> None:
        published.append(payload)

    bus.subscribe(EVENT_ACCOUNT_UPDATE, _capture)

    ex = FakeExchange(balance=_snap(Decimal("1200")), positions=[])
    svc = AccountService(
        exchange=ex,
        history_repo=AccountHistoryRepository(),
        position_repo=PositionRepository(),
        session_factory=open_session,
        event_bus=bus,
        initial_balance=Decimal("1000"),
    )

    persisted = await svc.record_snapshot()

    assert persisted.total_value == Decimal("1200")
    assert persisted.id is not None
    assert len(published) == 1
    # REAL-column round-trip can yield "1200.0" so accept any form of 1200.
    assert str(published[0]["total_value"]).startswith("1200")
    assert str(published[0]["peak"]).startswith("1200")
    assert Decimal(str(published[0]["drawdown_percent"])) == Decimal(0)


@pytest.mark.asyncio
async def test_peak_and_drawdown_track_across_snapshots() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    ex = FakeExchange(balance=_snap(Decimal("2000")), positions=[])
    svc = AccountService(
        exchange=ex,
        history_repo=AccountHistoryRepository(),
        position_repo=PositionRepository(),
        session_factory=open_session,
        event_bus=bus,
        initial_balance=Decimal("1000"),
    )

    # Seed a 2000 peak
    await svc.record_snapshot()

    # Now drop to 1500 → 25% drawdown
    ex._balance = _snap(Decimal("1500"))
    await svc.record_snapshot()

    snap_dict = await svc.current_snapshot()
    assert Decimal(str(snap_dict["peak"])) == Decimal(2000)
    assert Decimal(str(snap_dict["drawdown_percent"])) == Decimal(25)


@pytest.mark.asyncio
async def test_current_snapshot_without_history_falls_back_to_live() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    ex = FakeExchange(balance=_snap(Decimal("500")), positions=[])
    svc = AccountService(
        exchange=ex,
        history_repo=AccountHistoryRepository(),
        position_repo=PositionRepository(),
        session_factory=open_session,
        event_bus=bus,
        initial_balance=Decimal("500"),
    )

    snap_dict = await svc.current_snapshot()
    assert Decimal(str(snap_dict["total_value"])) == Decimal(500)
    assert Decimal(str(snap_dict["peak"])) == Decimal(500)
    assert Decimal(str(snap_dict["drawdown_percent"])) == Decimal(0)


def test_compute_sharpe_single_sample_returns_none() -> None:
    assert AccountService._compute_sharpe([Decimal("1")]) is None


def test_compute_sharpe_zero_variance_returns_none() -> None:
    vals = [Decimal("5")] * 5
    assert AccountService._compute_sharpe(vals) is None


def test_compute_sharpe_multi_sample() -> None:
    out = AccountService._compute_sharpe([Decimal("1"), Decimal("2"), Decimal("3")])
    assert out is not None
    assert out > 0
