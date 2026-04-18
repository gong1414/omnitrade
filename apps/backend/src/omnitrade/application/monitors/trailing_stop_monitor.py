"""TrailingStopMonitor — 3-level trailing stop ladder + peak_pnl update.

Each tick:

  1. Compute ``current_pnl_percent`` from position.unrealized_pnl + leverage.
  2. Lift ``trailing_peak_pnl_pct`` to ``max(old, current)`` — single atomic
     ``apply_three_way_state`` call (cumulative_close_pct + stop_loss
     held constant so the three-way invariant is preserved).
  3. Iterate the level ladder ``L3 → L2 → L1``; if
     ``trailing_peak_pnl_pct >= trigger`` AND ``current_pnl_percent <= stop_at``
     the trailing-stop fires and closes the position via
     ``PositionManager.close_position`` with reason ``trailing_stop``.

NOT folded — partial-profit logic lives in a different file
(``partial_profit_monitor.py``); keeping them separate simplifies the
close-path classifier and the per-loop scheduling contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.application.position_manager import PositionManager, SessionFactory
from omnitrade.domain.entities import Position
from omnitrade.domain.services.three_way_state import apply_three_way_state
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TrailingLevel:
    """One rung of the trailing-stop ladder (trigger %, stop-at %).

    Both fields are levered pnl percentages expressed as non-negative
    Decimal (e.g. Decimal("15") == 15%).
    """

    trigger: Decimal
    stop_at: Decimal


# Default ladder matches the ``arena-steward`` strategy (5→2 / 10→5 / 20→12).
# Production uses the strategy registry; this default keeps the monitor
# self-contained for tests.
DEFAULT_LEVELS: tuple[TrailingLevel, TrailingLevel, TrailingLevel] = (
    TrailingLevel(trigger=Decimal("5"), stop_at=Decimal("2")),
    TrailingLevel(trigger=Decimal("10"), stop_at=Decimal("5")),
    TrailingLevel(trigger=Decimal("20"), stop_at=Decimal("12")),
)


def compute_pnl_percent(position: Position) -> Decimal:
    """Return the levered pnl percentage for a position.

    pnl% = (unrealized_pnl / notional) * leverage * 100 where
    notional = entry_price * quantity.
    """
    notional = position.entry_price * position.quantity
    if notional <= Decimal(0):
        return Decimal(0)
    base = position.unrealized_pnl / notional
    return base * Decimal(position.leverage) * Decimal(100)


def pick_fired_level(
    peak: Decimal,
    current: Decimal,
    levels: tuple[TrailingLevel, TrailingLevel, TrailingLevel],
) -> TrailingLevel | None:
    """Iterate L3 → L2 → L1; return the first level whose trigger+stop fired."""
    for lvl in reversed(levels):
        if peak >= lvl.trigger and current <= lvl.stop_at:
            return lvl
    return None


class TrailingStopMonitor:
    """Periodic trailing-stop position monitor."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        position_repo: PositionRepository,
        session_factory: SessionFactory,
        position_manager: PositionManager,
        levels: tuple[TrailingLevel, TrailingLevel, TrailingLevel] = DEFAULT_LEVELS,
        clock: ClockProtocol | None = None,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._position_repo = position_repo
        self._session_factory = session_factory
        self._position_manager = position_manager
        self._levels = levels
        self._clock = clock or SystemClock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    async def _lift_peak(
        self, session: AsyncSession, position: Position, new_peak: Decimal
    ) -> None:
        if position.id is None:
            return
        # Atomic three-way UPDATE with only the peak lifted — partial_close
        # and stop_loss are held constant. We pre-compute a new domain
        # Position for log/audit symmetry (discarded).
        _ = apply_three_way_state(
            position,
            new_cumulative_close_pct=position.cumulative_close_pct,
            new_stop_loss=position.stop_loss,
            new_trailing_peak=new_peak,
        )
        await self._position_repo.apply_three_way_state(
            session,
            position.id,
            partial_close_pct=position.cumulative_close_pct,
            stop_loss=position.stop_loss,
            peak_pnl=new_peak,
        )

    async def tick(self) -> None:
        with_context(logger).info("trailing_stop_monitor.tick")
        session = await self._session_factory()
        to_close: list[str] = []
        try:
            positions = await self._position_repo.list_all(session)
            for pos in positions:
                current_pnl = compute_pnl_percent(pos)
                new_peak = max(pos.trailing_peak_pnl_pct, current_pnl)
                if new_peak != pos.trailing_peak_pnl_pct:
                    await self._lift_peak(session, pos, new_peak)

                fired = pick_fired_level(new_peak, current_pnl, self._levels)
                if fired is not None:
                    to_close.append(pos.symbol)
            await session.commit()
        finally:
            await session.close()

        for symbol in to_close:
            with_context(logger).info(
                "trailing_stop_monitor.fire",
                symbol=symbol,
            )
            await self._position_manager.close_position(
                symbol=symbol,
                reason="trailing_stop",
            )


__all__ = [
    "DEFAULT_LEVELS",
    "TrailingLevel",
    "TrailingStopMonitor",
    "compute_pnl_percent",
    "pick_fired_level",
]
