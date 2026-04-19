"""PriceSyncMonitor — mark-price sync for OPEN positions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omnitrade.application.monitors.price_sync_monitor import PriceSyncMonitor
from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.models import Base
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)

_NOW = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
    await engine.dispose()


class _FakeExchange:
    """Minimal stub exposing only ``fetch_positions``; other protocol methods unused."""

    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions
        self.calls = 0

    async def fetch_positions(self) -> list[Position]:
        self.calls += 1
        return self._positions

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)


def _session_factory_from(session: AsyncSession):
    async def _open() -> AsyncSession:
        return session

    return _open


def _make_position(**overrides) -> Position:
    defaults = dict(
        symbol="BTC_USDT",
        quantity=Decimal("0.001"),
        entry_price=Decimal("75000"),
        current_price=Decimal("75000"),
        liquidation_price=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        leverage=6,
        side="long",
        entry_order_id="order-1",
        opened_at=_NOW,
    )
    defaults.update(overrides)
    return Position(**defaults)


async def test_sync_updates_current_price_and_upnl(session: AsyncSession) -> None:
    """Stale stored price is refreshed; DB sees the exchange mark + upnl."""
    repo = PositionRepository()
    stored = _make_position()
    await repo.create(session, stored)
    await session.commit()

    fresh = _make_position(
        current_price=Decimal("76000"),
        unrealized_pnl=Decimal("1.0"),
    )
    monitor = PriceSyncMonitor(
        interval_seconds=15,
        exchange=_FakeExchange([fresh]),
        position_repo=repo,
        session_factory=_session_factory_from(session),
    )

    await monitor.tick()

    refreshed = await repo.get_by_symbol(session, "BTC_USDT")
    assert refreshed is not None
    assert refreshed.current_price == Decimal("76000")
    assert refreshed.unrealized_pnl == Decimal("1.0")


async def test_sync_reconciles_positions_not_on_exchange(session: AsyncSession) -> None:
    """Positions absent from the exchange response are soft-closed (cum=100)."""
    repo = PositionRepository()
    eth = _make_position(symbol="ETH_USDT", entry_price=Decimal("3000"),
                         current_price=Decimal("3000"))
    await repo.create(session, eth)
    await session.commit()

    monitor = PriceSyncMonitor(
        interval_seconds=15,
        exchange=_FakeExchange([]),  # empty — exchange shows no positions
        position_repo=repo,
        session_factory=_session_factory_from(session),
    )
    await monitor.tick()

    reconciled = await repo.get_by_symbol(session, "ETH_USDT")
    assert reconciled is not None
    # Soft-closed: cumulative_close_pct == 100, entry price untouched.
    assert reconciled.cumulative_close_pct == Decimal(100)


async def test_fallback_upnl_when_exchange_returns_zero(session: AsyncSession) -> None:
    """If the exchange reports upnl=0 but the mark moved, compute PnL locally."""
    repo = PositionRepository()
    stored = _make_position(
        symbol="BTC_USDT",
        entry_price=Decimal("75000"),
        quantity=Decimal("0.002"),
        side="long",
    )
    await repo.create(session, stored)
    await session.commit()

    fresh = _make_position(
        symbol="BTC_USDT",
        entry_price=Decimal("75000"),
        quantity=Decimal("0.002"),
        current_price=Decimal("76000"),
        unrealized_pnl=Decimal("0"),  # exchange didn't fill in upnl
        side="long",
    )
    monitor = PriceSyncMonitor(
        interval_seconds=15,
        exchange=_FakeExchange([fresh]),
        position_repo=repo,
        session_factory=_session_factory_from(session),
    )
    await monitor.tick()

    refreshed = await repo.get_by_symbol(session, "BTC_USDT")
    assert refreshed is not None
    # (76000 - 75000) * 0.002 * 1 = 2.0
    assert refreshed.unrealized_pnl == Decimal("2.0")


async def test_sync_survives_exchange_failure(session: AsyncSession) -> None:
    """Exchange exception is logged and swallowed — no crash, no DB write."""
    repo = PositionRepository()
    stored = _make_position()
    await repo.create(session, stored)
    await session.commit()

    class _Boom:
        async def fetch_positions(self) -> list[Position]:
            raise RuntimeError("exchange down")

        def __getattr__(self, name: str) -> Any:
            raise AttributeError(name)

    monitor = PriceSyncMonitor(
        interval_seconds=15,
        exchange=_Boom(),
        position_repo=repo,
        session_factory=_session_factory_from(session),
    )
    # Should not raise.
    await monitor.tick()

    unchanged = await repo.get_by_symbol(session, "BTC_USDT")
    assert unchanged is not None
    assert unchanged.current_price == Decimal("75000")
