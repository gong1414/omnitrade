"""StopLossMonitor — extreme stop-loss + per-position stop_loss override.

Applies two rules each tick:
  1. ``EXTREME_STOP_LOSS_PERCENT`` (default -30%) hard floor — if the
     levered pnl% falls below this, the position closes immediately with
     ``reason='stop_loss'``.
  2. Per-position ``stop_loss`` override (negative %); when
     ``current_pnl_percent <= override`` the position closes.

Cadence: 10 seconds (``interval_seconds=10``) — short-tick cadence is the
baseline for hard-floor stop-loss detection.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.application.monitors.trailing_stop_monitor import compute_pnl_percent
from omnitrade.application.position_manager import PositionManager, SessionFactory
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class StopLossMonitor:
    """Periodic stop-loss position monitor."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        extreme_stop_loss_percent: Decimal,
        position_repo: PositionRepository,
        session_factory: SessionFactory,
        position_manager: PositionManager,
        clock: ClockProtocol | None = None,
    ) -> None:
        self._interval_seconds = interval_seconds
        # Normalise the extreme threshold into a strictly-negative Decimal.
        # A positive input is clamped to its negative twin so the rule
        # "pnl < threshold" is always a loss trigger.
        if extreme_stop_loss_percent > Decimal(0):
            extreme_stop_loss_percent = -extreme_stop_loss_percent
        self._extreme = extreme_stop_loss_percent
        self._position_repo = position_repo
        self._session_factory = session_factory
        self._position_manager = position_manager
        self._clock = clock or SystemClock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    async def tick(self) -> None:
        with_context(logger).info("stop_loss_monitor.tick")
        session = await self._session_factory()
        try:
            positions = await self._position_repo.list_all(session)
        finally:
            await session.close()

        to_close: list[tuple[str, str]] = []  # (symbol, reason)
        for pos in positions:
            pnl = compute_pnl_percent(pos)
            if pnl <= self._extreme:
                to_close.append((pos.symbol, "extreme_stop_loss"))
                continue
            override = pos.stop_loss
            if override is not None:
                if override < Decimal(0):
                    # Negative value = percentage threshold (legacy path).
                    if pnl <= override:
                        to_close.append((pos.symbol, "stop_loss"))
                else:
                    # Positive value = price level.
                    price_hit = (
                        pos.current_price <= override
                        if pos.side == "long"
                        else pos.current_price >= override
                    )
                    if price_hit:
                        to_close.append((pos.symbol, "stop_loss"))

        for symbol, reason in to_close:
            with_context(logger).info(
                "stop_loss_monitor.fire",
                symbol=symbol,
                reason=reason,
            )
            await self._position_manager.close_position(symbol=symbol, reason=reason)


__all__ = ["StopLossMonitor"]
