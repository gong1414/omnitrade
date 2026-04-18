"""PositionManager — open / close / partial_close paths + atomic 3-way state."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.events import EVENT_POSITION_UPDATE, EventBus
from omnitrade.application.position_manager import PositionManager
from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from tests.application._fakes import (
    FakeExchange,
    build_sqlite_session_factory,
    make_trade,
)


async def _seed_position(open_session, symbol: str = "BTC_USDT") -> Position:
    pos = Position(
        symbol=symbol,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        liquidation_price=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        leverage=5,
        side="long",
        stop_loss=Decimal("-5"),
        entry_order_id="ord-seed",
        opened_at=datetime(2026, 4, 18, tzinfo=UTC),
        trailing_peak_pnl_pct=Decimal("0"),
        cumulative_close_pct=Decimal("0"),
    )
    session = await open_session()
    try:
        repo = PositionRepository()
        persisted = await repo.create(session, pos)
        await session.commit()
    finally:
        await session.close()
    return persisted


@pytest.mark.asyncio
async def test_open_position_records_trade_position_and_emits_event() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    published: list[dict[str, object]] = []

    async def _capture(payload: dict[str, object]) -> None:
        published.append(payload)

    bus.subscribe(EVENT_POSITION_UPDATE, _capture)

    trade = make_trade(order_id="ord-1", ttype="open")
    ex = FakeExchange(place_order_trade=trade, close_trade=None)
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    out = await mgr.open_position(
        symbol="BTC_USDT",
        side="long",
        size=Decimal("1"),
        leverage=5,
    )
    assert out.order_id == "ord-1"
    assert len(published) == 1
    assert published[0]["action"] == "open"


@pytest.mark.asyncio
async def test_close_position_calls_apply_three_way_state() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    await _seed_position(open_session)
    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(order_id="ord-close", ttype="close"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    trade = await mgr.close_position(symbol="BTC_USDT", reason="ai_decision")
    assert trade.order_id == "ord-close"

    # Verify the three-way state UPDATE landed (cumulative_close_pct == 100).
    session = await open_session()
    try:
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    assert pos.cumulative_close_pct == Decimal("100")
    assert pos.stop_loss is None


@pytest.mark.asyncio
async def test_partial_close_updates_cumulative_and_stop_loss() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    await _seed_position(open_session)
    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(order_id="ord-pc", ttype="close"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    await mgr.partial_close(
        symbol="BTC_USDT",
        percentage=Decimal("30"),
        new_stop_loss=Decimal("-2"),
        reason="partial_profit",
    )
    await mgr.partial_close(
        symbol="BTC_USDT",
        percentage=Decimal("40"),
        new_stop_loss=Decimal("-1"),
        reason="partial_profit",
    )

    session = await open_session()
    try:
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    assert pos.cumulative_close_pct == Decimal("70")
    assert pos.stop_loss == Decimal("-1")


@pytest.mark.asyncio
async def test_partial_close_saturates_at_100() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    await _seed_position(open_session)
    bus = EventBus()
    ex = FakeExchange(close_trade=make_trade(order_id="ord-pc2", ttype="close"))
    mgr = PositionManager(
        exchange=ex,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    await mgr.partial_close(symbol="BTC_USDT", percentage=Decimal("60"))
    await mgr.partial_close(symbol="BTC_USDT", percentage=Decimal("60"))

    session = await open_session()
    try:
        pos = await PositionRepository().get_by_symbol(session, "BTC_USDT")
    finally:
        await session.close()
    assert pos is not None
    assert pos.cumulative_close_pct == Decimal("100")


@pytest.mark.asyncio
async def test_partial_close_rejects_out_of_range() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    mgr = PositionManager(
        exchange=FakeExchange(close_trade=make_trade(ttype="close")),
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=bus,
    )
    with pytest.raises(ValueError, match="partial_close percentage"):
        await mgr.partial_close(symbol="BTC_USDT", percentage=Decimal("0"))
    with pytest.raises(ValueError, match="partial_close percentage"):
        await mgr.partial_close(symbol="BTC_USDT", percentage=Decimal("150"))
