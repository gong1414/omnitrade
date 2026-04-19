"""PriceSyncMonitor — keep ``positions.current_price`` fresh from the exchange.

Without this monitor, ``current_price`` is frozen at open time
(``position_manager.open_position`` sets it and nothing else writes it),
which in turn pins ``unrealized_pnl`` at 0 and blinds:

* The dashboard (PnL / PositionsTable mark column reads the DB).
* ``StopLossMonitor`` — its ``price_hit`` rule compares ``pos.current_price``
  against the override level, so a stale price means stop-loss triggers
  only ever fire when the trading cycle happens to resync.

This monitor ticks every ``price_sync_interval_seconds`` (default 15 s),
pulls ``exchange.fetch_positions()`` once (cheaper than one ticker fetch
per symbol), matches by symbol, and writes ``current_price`` +
``unrealized_pnl`` via the targeted ``apply_mark_price`` UPDATE so the
three-way state contract stays untouched.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.application.position_manager import SessionFactory
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class PriceSyncMonitor:
    """Periodic mark-price sync for all open positions."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        exchange: ExchangeClient,
        position_repo: PositionRepository,
        session_factory: SessionFactory,
        clock: ClockProtocol | None = None,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._exchange = exchange
        self._position_repo = position_repo
        self._session_factory = session_factory
        self._clock = clock or SystemClock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    async def tick(self) -> None:
        with_context(logger).debug("price_sync_monitor.tick")
        try:
            fresh_positions = await self._exchange.fetch_positions()
        except Exception as exc:
            with_context(logger).warning(
                "price_sync_monitor.fetch_failed",
                error=str(exc),
            )
            return

        if not fresh_positions:
            return
        by_symbol = {p.symbol: p for p in fresh_positions}

        session = await self._session_factory()
        updated = 0
        try:
            stored = await self._position_repo.list_all(session)
            for pos in stored:
                if pos.id is None:
                    continue
                fresh = by_symbol.get(pos.symbol)
                if fresh is None:
                    continue
                new_price = fresh.current_price
                new_upnl = self._compute_upnl(pos.side, pos.entry_price, new_price, pos.quantity) \
                    if fresh.unrealized_pnl == Decimal(0) else fresh.unrealized_pnl
                # Skip no-op writes to keep the row version stable.
                if new_price == pos.current_price and new_upnl == pos.unrealized_pnl:
                    continue
                await self._position_repo.apply_mark_price(
                    session,
                    pos.id,
                    current_price=new_price,
                    unrealized_pnl=new_upnl,
                )
                updated += 1
            if updated:
                await session.commit()
        finally:
            await session.close()

        if updated:
            with_context(logger).info(
                "price_sync_monitor.synced",
                updated=updated,
            )

    @staticmethod
    def _compute_upnl(
        side: str,
        entry: Decimal,
        mark: Decimal,
        qty: Decimal,
    ) -> Decimal:
        """Fallback PnL if the exchange adapter returns 0 (unlevered)."""
        direction = Decimal(1) if side == "long" else Decimal(-1)
        return (mark - entry) * qty * direction


__all__ = ["PriceSyncMonitor"]
