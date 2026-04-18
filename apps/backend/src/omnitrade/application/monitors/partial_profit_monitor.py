"""PartialProfitMonitor — 3-stage partial take-profit ladder.

**Explicitly NOT folded into ``trailing_stop_monitor``** per consensus
plan §7 R1. Each tick:

  1. Compute ``current_pnl_percent``.
  2. Walk the 3 stages (3%, 6%, 10%); the next unhit stage whose
     ``trigger <= current_pnl`` fires and closes a percentage of the
     original quantity.
  3. Atomic three-way UPDATE via ``PositionRepository.apply_three_way_state``:
     - ``cumulative_close_pct`` lifted to the stage's cumulative close %
     - ``stop_loss`` tightened via ``get_profit_protection_stop_percent``
     - ``trailing_peak_pnl_pct`` lifted to the stage trigger

Grep gate: this file must contain ``cumulative_close_pct`` — the
trailing-stop file must NOT.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.application.monitors.trailing_stop_monitor import compute_pnl_percent
from omnitrade.application.position_manager import PositionManager, SessionFactory
from omnitrade.domain.entities import Position
from omnitrade.domain.services.three_way_state import (
    apply_three_way_state,
    get_profit_protection_stop_percent,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PartialStage:
    """One stage of the partial-profit ladder.

    ``trigger`` = levered pnl % that must be exceeded.
    ``cumulative_close_percent`` = cumulative cumulative_close_pct after
    this stage fires (0..100).
    """

    trigger: Decimal
    cumulative_close_percent: Decimal


# Default 3%/6%/10% ladder with 30%/60%/100% cumulative closes — matches the
# upstream ``arena-steward``-ish configuration; production wires strategy-specific
# stages via the strategy registry.
DEFAULT_STAGES: tuple[PartialStage, PartialStage, PartialStage] = (
    PartialStage(trigger=Decimal("3"), cumulative_close_percent=Decimal("30")),
    PartialStage(trigger=Decimal("6"), cumulative_close_percent=Decimal("60")),
    PartialStage(trigger=Decimal("10"), cumulative_close_percent=Decimal("100")),
)


def pick_next_stage(
    position: Position,
    current_pnl: Decimal,
    stages: tuple[PartialStage, PartialStage, PartialStage],
) -> tuple[int, PartialStage] | None:
    """Find the next unhit stage whose trigger is below current pnl."""
    closed = position.cumulative_close_pct
    for idx, stage in enumerate(stages):
        if closed >= stage.cumulative_close_percent:
            continue
        if current_pnl >= stage.trigger:
            return idx, stage
    return None


class PartialProfitMonitor:
    """Periodic partial-profit monitor (NOT folded)."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        position_repo: PositionRepository,
        session_factory: SessionFactory,
        position_manager: PositionManager,
        stages: tuple[PartialStage, PartialStage, PartialStage] = DEFAULT_STAGES,
        clock: ClockProtocol | None = None,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._position_repo = position_repo
        self._session_factory = session_factory
        self._position_manager = position_manager
        self._stages = stages
        self._clock = clock or SystemClock()

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    async def _apply_stage(
        self,
        session: AsyncSession,
        position: Position,
        stage: PartialStage,
        stage_index: int,
    ) -> tuple[Decimal, Decimal]:
        """Atomic three-way UPDATE for a triggered stage.

        Returns ``(delta_close_percent, new_stop_loss)``.
        """
        assert position.id is not None
        delta = stage.cumulative_close_percent - position.cumulative_close_pct
        new_stop = get_profit_protection_stop_percent(stage.trigger, stage_index)
        # Keep the domain copy symmetric with the persistence write.
        _ = apply_three_way_state(
            position,
            new_cumulative_close_pct=stage.cumulative_close_percent,
            new_stop_loss=new_stop,
            new_trailing_peak=max(position.trailing_peak_pnl_pct, stage.trigger),
        )
        await self._position_repo.apply_three_way_state(
            session,
            position.id,
            partial_close_pct=stage.cumulative_close_percent,
            stop_loss=new_stop,
            peak_pnl=max(position.trailing_peak_pnl_pct, stage.trigger),
        )
        return delta, new_stop

    async def tick(self) -> None:
        with_context(logger).info("partial_profit_monitor.tick")
        # First pass: apply three-way-state updates + collect close orders.
        close_orders: list[tuple[str, Decimal, Decimal]] = []  # (symbol, pct, new_sl)
        session = await self._session_factory()
        try:
            positions = await self._position_repo.list_all(session)
            for pos in positions:
                if pos.id is None:
                    continue
                current = compute_pnl_percent(pos)
                picked = pick_next_stage(pos, current, self._stages)
                if picked is None:
                    continue
                idx, stage = picked
                delta, new_stop = await self._apply_stage(session, pos, stage, idx)
                if delta > Decimal(0):
                    close_orders.append((pos.symbol, delta, new_stop))
            await session.commit()
        finally:
            await session.close()

        # Second pass: market-side partial closes (outside the session window).
        for symbol, pct, new_stop in close_orders:
            with_context(logger).info(
                "partial_profit_monitor.fire",
                symbol=symbol,
                percentage=str(pct),
            )
            await self._position_manager.partial_close(
                symbol=symbol,
                percentage=pct,
                new_stop_loss=new_stop,
                reason="partial_profit",
            )


__all__ = [
    "DEFAULT_STAGES",
    "PartialProfitMonitor",
    "PartialStage",
    "pick_next_stage",
]
