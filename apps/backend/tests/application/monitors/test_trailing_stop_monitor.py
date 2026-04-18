"""TrailingStopMonitor — peak lift + 3-level ladder close."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.events import EventBus
from omnitrade.application.monitors.trailing_stop_monitor import (
    DEFAULT_LEVELS,
    TrailingLevel,
    TrailingStopMonitor,
    compute_pnl_percent,
    pick_fired_level,
)
from omnitrade.application.position_manager import PositionManager
from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from tests.application._fakes import (
    FakeClock,
    FakeExchange,
    build_sqlite_session_factory,
    make_trade,
)


def _pos(**kwargs: object) -> Position:
    base = {
        "symbol": "BTC_USDT",
        "quantity": Decimal("1"),
        "entry_price": Decimal("100"),
        "current_price": Decimal("100"),
        "liquidation_price": Decimal("0"),
        "unrealized_pnl": Decimal("0"),
        "leverage": 5,
        "side": "long",
        "entry_order_id": "ord-seed",
        "opened_at": datetime(2026, 4, 18, tzinfo=UTC),
        "trailing_peak_pnl_pct": Decimal("0"),
        "cumulative_close_pct": Decimal("0"),
    }
    base.update(kwargs)
    return Position(**base)  # type: ignore[arg-type]


def test_compute_pnl_percent_zero_notional() -> None:
    p = _pos(quantity=Decimal("0"))
    assert compute_pnl_percent(p) == Decimal(0)


def test_compute_pnl_percent_levered() -> None:
    # notional = 100, pnl = 5 → 5% base × 5x leverage = 25%
    p = _pos(unrealized_pnl=Decimal("5"), leverage=5)
    assert compute_pnl_percent(p) == Decimal(25)


def test_pick_fired_level_picks_highest_hit() -> None:
    # peak 25 (≥ L3 trigger 20) AND current 10 (≤ L3 stop_at 12) → L3 fires
    fired = pick_fired_level(Decimal("25"), Decimal("10"), DEFAULT_LEVELS)
    assert fired == TrailingLevel(trigger=Decimal("20"), stop_at=Decimal("12"))


def test_pick_fired_level_no_hit() -> None:
    # peak 3, current 1 — below L1 trigger (5)
    fired = pick_fired_level(Decimal("3"), Decimal("1"), DEFAULT_LEVELS)
    assert fired is None


@pytest.mark.asyncio
async def test_tick_lifts_peak_without_firing() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # Seed a position with current pnl 4% (< L1 trigger 5%)
    session = await open_session()
    try:
        repo = PositionRepository()
        await repo.create(session, _pos(unrealized_pnl=Decimal("0.8"), leverage=5))
        await session.commit()
    finally:
        await session.close()

    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(ttype="close"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    mon = TrailingStopMonitor(
        interval_seconds=10,
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
        clock=FakeClock(),
    )

    await mon.tick()

    session = await open_session()
    try:
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    assert pos.trailing_peak_pnl_pct == Decimal("4")  # pnl% = 0.8/100 * 5 * 100 = 4
    # No close fired.
    assert ex.close_calls == []


@pytest.mark.asyncio
async def test_tick_fires_level_closes_position() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # Position with peak 30, current 5 → L3 fires (peak ≥ 20, current ≤ 12).
    session = await open_session()
    try:
        repo = PositionRepository()
        await repo.create(
            session,
            _pos(
                unrealized_pnl=Decimal("1"),  # 1/100 * 5 * 100 = 5% current
                leverage=5,
                trailing_peak_pnl_pct=Decimal("30"),
            ),
        )
        await session.commit()
    finally:
        await session.close()

    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(ttype="close", order_id="ord-tr"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    mon = TrailingStopMonitor(
        interval_seconds=10,
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
    )

    await mon.tick()

    # Exchange saw a close call with 100%.
    assert len(ex.close_calls) == 1
    assert ex.close_calls[0]["percentage"] == 100.0

    # Position row exists (soft-close), cumulative_close_pct == 100.
    session = await open_session()
    try:
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    assert pos.cumulative_close_pct == Decimal("100")
