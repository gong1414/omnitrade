"""Shared in-memory test doubles for application-layer unit tests.

Provides:
  * ``FakeClock`` — deterministic ``ClockProtocol`` for monitor tests.
  * ``FakeExchange`` — ``ExchangeClient`` stub returning scripted balances / trades.
  * ``FakeEventBus`` — captures published events for assertion.
  * ``build_sqlite_session_factory`` — in-memory SQLite with the Phase-3 schema
    so application-service tests exercise the real repositories.

These replace network/DB boundaries; monitor-specific clocks + the exchange
stub are deliberately tiny so tests stay readable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omnitrade.domain.entities import AccountSnapshot, Position, Trade
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol
from omnitrade.infrastructure.persistence.models import Base


class FakeClock:
    """Deterministic ``ClockProtocol`` — advance time manually via ``tick``."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start if start is not None else datetime(2026, 4, 18, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def tick(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


assert issubclass(FakeClock, object)  # runtime_checkable ClockProtocol sanity


class FakeExchange:
    """Minimal ``ExchangeClient`` stub backed by constructor-supplied data."""

    def __init__(
        self,
        *,
        balance: AccountSnapshot | None = None,
        positions: list[Position] | None = None,
        place_order_trade: Trade | None = None,
        close_trade: Trade | None = None,
    ) -> None:
        self._balance = balance
        self._positions = list(positions or [])
        self._place_order_trade = place_order_trade
        self._close_trade = close_trade
        self.place_order_calls: list[dict[str, Any]] = []
        self.close_calls: list[dict[str, Any]] = []

    async def fetch_balance(self) -> AccountSnapshot:
        if self._balance is None:
            raise RuntimeError("FakeExchange.balance not configured")
        return self._balance

    async def fetch_positions(self) -> list[Position]:
        return list(self._positions)

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade:
        self.place_order_calls.append(
            {
                "symbol": str(symbol),
                "side": side,
                "size": size,
                "leverage": int(leverage),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )
        if self._place_order_trade is None:
            raise RuntimeError("FakeExchange.place_order_trade not configured")
        return self._place_order_trade

    async def close_position(
        self,
        position_id: str,
        percentage: Percentage,
    ) -> Trade:
        self.close_calls.append({"position_id": position_id, "percentage": percentage.value})
        if self._close_trade is None:
            raise RuntimeError("FakeExchange.close_trade not configured")
        return self._close_trade

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]:
        return {"symbol": str(symbol), "last": 0.0}

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        return []


class FakeEventBus:
    """Captures every publish for assertion.

    Does NOT implement subscribe_queue; tests that need queue fan-out should
    use the real ``EventBus``.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, payload))

    def subscribe(
        self,
        event_name: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        # unused in unit tests
        return None


def make_position(
    *,
    pid: int = 1,
    symbol: str = "BTC_USDT",
    side: str = "long",
    quantity: Decimal = Decimal("1"),
    entry_price: Decimal = Decimal("100"),
    current_price: Decimal = Decimal("100"),
    leverage: int = 5,
    unrealized_pnl: Decimal = Decimal("0"),
    stop_loss: Decimal | None = None,
    trailing_peak_pnl_pct: Decimal = Decimal("0"),
    cumulative_close_pct: Decimal = Decimal("0"),
) -> Position:
    """Ergonomic ``Position`` factory with sensible defaults."""
    return Position(
        id=pid,
        symbol=symbol,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
        liquidation_price=Decimal("0"),
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
        side=side,
        stop_loss=stop_loss,
        entry_order_id=f"ord-{pid}",
        opened_at=datetime(2026, 4, 18, tzinfo=UTC),
        trailing_peak_pnl_pct=trailing_peak_pnl_pct,
        cumulative_close_pct=cumulative_close_pct,
    )


def make_trade(
    *,
    order_id: str = "ord-1",
    symbol: str = "BTC_USDT",
    side: str = "long",
    ttype: str = "open",
    price: Decimal = Decimal("100"),
    quantity: Decimal = Decimal("1"),
    leverage: int = 5,
    fee: Decimal | None = Decimal("0.05"),
    timestamp: datetime | None = None,
) -> Trade:
    return Trade(
        order_id=order_id,
        symbol=symbol,
        side=side,
        type=ttype,
        price=price,
        quantity=quantity,
        leverage=leverage,
        fee=fee,
        timestamp=timestamp or datetime(2026, 4, 18, tzinfo=UTC),
        status="filled",
    )


async def build_sqlite_session_factory() -> tuple[
    async_sessionmaker[AsyncSession], Callable[[], Awaitable[AsyncSession]]
]:
    """Spin up an in-memory SQLite engine + Phase-3 schema.

    Returns (session_factory, open_session_coro) — the second is a bound
    coroutine suitable as the ``SessionFactory`` alias used by
    ``application.*`` services.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def open_session() -> AsyncSession:
        return factory()

    return factory, open_session


__all__ = [
    "FakeClock",
    "FakeEventBus",
    "FakeExchange",
    "build_sqlite_session_factory",
    "make_position",
    "make_trade",
]
