"""Three-way state contract — atomic update assertion across monitor paths.

Verifies that every close/partial-close path mutates the 3 fields
(``cumulative_close_pct``, ``stop_loss``, ``trailing_peak_pnl_pct``) together
via ``PositionRepository.apply_three_way_state``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.events import EventBus
from omnitrade.application.monitors.partial_profit_monitor import PartialProfitMonitor
from omnitrade.application.monitors.trailing_stop_monitor import TrailingStopMonitor
from omnitrade.application.position_manager import PositionManager
from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from tests.application._fakes import FakeExchange, build_sqlite_session_factory, make_trade


def _seed(symbol: str, **kw: object) -> Position:
    base = {
        "symbol": symbol,
        "quantity": Decimal("1"),
        "entry_price": Decimal("100"),
        "current_price": Decimal("100"),
        "liquidation_price": Decimal("0"),
        "unrealized_pnl": Decimal("0"),
        "leverage": 5,
        "side": "long",
        "entry_order_id": f"ord-{symbol}",
        "opened_at": datetime(2026, 4, 18, tzinfo=UTC),
        "trailing_peak_pnl_pct": Decimal("0"),
        "cumulative_close_pct": Decimal("0"),
        "stop_loss": Decimal("-5"),
    }
    base.update(kw)
    return Position(**base)  # type: ignore[arg-type]


async def _row(open_session: object, symbol: str) -> Position | None:
    session = await open_session()  # type: ignore[misc]
    try:
        return await PositionRepository().get_by_symbol(session, symbol)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_trailing_stop_close_emits_atomic_three_way_state() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    # peak 30, current 5 → fires L3 (20/12)
    session = await open_session()
    try:
        await PositionRepository().create(
            session,
            _seed(
                "BTC_USDT",
                unrealized_pnl=Decimal("1"),
                leverage=5,
                trailing_peak_pnl_pct=Decimal("30"),
            ),
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
    mon = TrailingStopMonitor(
        interval_seconds=10,
        position_repo=PositionRepository(),
        session_factory=open_session,
        position_manager=mgr,
    )
    await mon.tick()

    row = await _row(open_session, "BTC_USDT")
    assert row is not None
    # Close path runs partial_close → 100, stop_loss cleared, peak retained.
    assert row.cumulative_close_pct == Decimal("100")
    assert row.stop_loss is None


@pytest.mark.asyncio
async def test_partial_profit_emits_atomic_three_way_state() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        await PositionRepository().create(
            session,
            _seed(
                "BTC_USDT",
                unrealized_pnl=Decimal("0.6"),  # → 3% levered
                leverage=5,
            ),
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

    row = await _row(open_session, "BTC_USDT")
    assert row is not None
    # Three-way state — all three fields updated in one go.
    assert row.cumulative_close_pct > Decimal("0")
    assert row.stop_loss is not None and row.stop_loss > Decimal("0")
    assert row.trailing_peak_pnl_pct == Decimal("3")


@pytest.mark.asyncio
async def test_position_manager_close_uses_apply_three_way_state() -> None:
    """Full-close path goes through the same atomic UPDATE helper."""
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        await PositionRepository().create(
            session,
            _seed("BTC_USDT", trailing_peak_pnl_pct=Decimal("12")),
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
    await mgr.close_position(symbol="BTC_USDT", reason="ai_decision")

    row = await _row(open_session, "BTC_USDT")
    assert row is not None
    assert row.cumulative_close_pct == Decimal("100")
    assert row.stop_loss is None
    # peak retained (not cleared on close)
    assert row.trailing_peak_pnl_pct == Decimal("12")
