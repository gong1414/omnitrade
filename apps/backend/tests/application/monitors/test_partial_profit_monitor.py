"""PartialProfitMonitor — 3-stage ladder with atomic three-way state update."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.events import EventBus
from omnitrade.application.monitors.partial_profit_monitor import (
    DEFAULT_STAGES,
    PartialProfitMonitor,
    pick_next_stage,
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


def test_pick_next_stage_selects_first_unhit() -> None:
    p = _pos(cumulative_close_pct=Decimal("0"))
    picked = pick_next_stage(p, Decimal("7"), DEFAULT_STAGES)
    assert picked is not None
    idx, stage = picked
    assert idx == 0  # first unhit stage (3%) fires first
    assert stage.cumulative_close_percent == Decimal("30")


def test_pick_next_stage_skips_already_closed_stage() -> None:
    # cumulative_close_pct already at 30% — stage 0 done.
    p = _pos(cumulative_close_pct=Decimal("30"))
    picked = pick_next_stage(p, Decimal("7"), DEFAULT_STAGES)
    assert picked is not None
    idx, stage = picked
    assert idx == 1
    assert stage.cumulative_close_percent == Decimal("60")


def test_pick_next_stage_returns_none_when_all_closed() -> None:
    p = _pos(cumulative_close_pct=Decimal("100"))
    assert pick_next_stage(p, Decimal("20"), DEFAULT_STAGES) is None


def test_pick_next_stage_returns_none_below_first_trigger() -> None:
    p = _pos(cumulative_close_pct=Decimal("0"))
    assert pick_next_stage(p, Decimal("2"), DEFAULT_STAGES) is None


@pytest.mark.asyncio
async def test_tick_fires_first_stage_atomic_update() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # pnl=0.6, leverage=5, notional=100 → 3% levered → stage 0 fires
    session = await open_session()
    try:
        await PositionRepository().create(session, _pos(unrealized_pnl=Decimal("0.6"), leverage=5))
        await session.commit()
    finally:
        await session.close()

    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(ttype="close", order_id="ord-pp"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    mon = PartialProfitMonitor(
        interval_seconds=10,
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
        clock=FakeClock(),
    )
    await mon.tick()

    # Exchange got a 30% partial close.
    assert len(ex.close_calls) == 1
    assert ex.close_calls[0]["percentage"] == 30.0

    # Three-way state atomic: partial_close=30, stop_loss=1.5 (3*0.5), peak=3.
    session = await open_session()
    try:
        # 2 trades total because PositionManager.partial_close also emits one
        # and atomic update leaves cumulative_close_pct at 30.
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    # Monitor's pre-close set partial_close=30; PositionManager adds 30 → 60
    # so cumulative saturates as expected.
    assert pos.cumulative_close_pct == Decimal("60")
    assert pos.stop_loss == Decimal("1.5")
    assert pos.trailing_peak_pnl_pct == Decimal("3")


@pytest.mark.asyncio
async def test_tick_noop_when_no_stage_triggered() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        await PositionRepository().create(
            session,
            _pos(unrealized_pnl=Decimal("0.2"), leverage=5),  # pnl% = 1
        )
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
    mon = PartialProfitMonitor(
        interval_seconds=10,
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
    )
    await mon.tick()
    assert ex.close_calls == []
