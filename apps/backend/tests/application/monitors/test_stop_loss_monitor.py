"""StopLossMonitor — extreme + per-position override triggers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.events import EventBus
from omnitrade.application.monitors.stop_loss_monitor import StopLossMonitor
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


def _pos(symbol: str, pnl: Decimal, leverage: int, stop_loss: Decimal | None) -> Position:
    return Position(
        symbol=symbol,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        liquidation_price=Decimal("0"),
        unrealized_pnl=pnl,
        leverage=leverage,
        side="long",
        stop_loss=stop_loss,
        entry_order_id=f"ord-{symbol}",
        opened_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_tick_ignores_healthy_positions() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        await PositionRepository().create(session, _pos("BTC_USDT", Decimal("1"), 5, None))
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
    mon = StopLossMonitor(
        interval_seconds=10,
        extreme_stop_loss_percent=Decimal("-30"),
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
        clock=FakeClock(),
    )

    await mon.tick()
    assert ex.close_calls == []


@pytest.mark.asyncio
async def test_tick_fires_extreme_stop_loss() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # pnl=-8, notional=100, leverage=5 → -40% levered — trips -30%
    session = await open_session()
    try:
        await PositionRepository().create(session, _pos("BTC_USDT", Decimal("-8"), 5, None))
        await session.commit()
    finally:
        await session.close()

    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(ttype="close", order_id="ord-sl"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    mon = StopLossMonitor(
        interval_seconds=10,
        extreme_stop_loss_percent=Decimal("-30"),
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
    )
    await mon.tick()
    assert len(ex.close_calls) == 1


@pytest.mark.asyncio
async def test_tick_fires_per_position_override() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # pnl=-1, leverage=5 → -5% levered; override = -3%
    session = await open_session()
    try:
        await PositionRepository().create(
            session, _pos("BTC_USDT", Decimal("-1"), 5, Decimal("-3"))
        )
        await session.commit()
    finally:
        await session.close()

    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(ttype="close", order_id="ord-override"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    mon = StopLossMonitor(
        interval_seconds=10,
        extreme_stop_loss_percent=Decimal("-30"),
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
    )
    await mon.tick()
    assert len(ex.close_calls) == 1


def test_positive_extreme_threshold_is_flipped_to_negative() -> None:
    _factory = None  # unused
    mon = StopLossMonitor(
        interval_seconds=10,
        extreme_stop_loss_percent=Decimal("30"),
        position_repo=PositionRepository(),
        session_factory=lambda: None,  # type: ignore[arg-type, return-value]
        position_manager=None,  # type: ignore[arg-type]
    )
    # Access private for assertion only — validates normalisation behaviour.
    assert mon._extreme == Decimal("-30")
