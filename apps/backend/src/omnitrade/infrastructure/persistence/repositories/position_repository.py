"""PositionRepository — CRUD + atomic three-way state update.

apply_three_way_state() emits a single UPDATE statement (no SELECT before UPDATE)
to atomically update cumulative_close_pct, stop_loss, trailing_peak_pnl_pct together.
See ``omnitrade.domain.services.three_way_state`` for the invariant this closure enforces.
"""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.models import PositionORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: PositionORM) -> Position:
    return Position(
        id=row.id,
        symbol=row.symbol,
        quantity=Decimal(str(row.quantity)),
        entry_price=Decimal(str(row.entry_price)),
        current_price=Decimal(str(row.current_price)),
        liquidation_price=Decimal(str(row.liquidation_price)),
        unrealized_pnl=Decimal(str(row.unrealized_pnl)),
        leverage=row.leverage,
        side=row.side,
        profit_target=Decimal(str(row.profit_target)) if row.profit_target is not None else None,
        stop_loss=Decimal(str(row.stop_loss)) if row.stop_loss is not None else None,
        tp_order_id=row.tp_order_id,
        sl_order_id=row.sl_order_id,
        entry_order_id=row.entry_order_id,
        opened_at=row.opened_at,
        confidence=Decimal(str(row.confidence)) if row.confidence is not None else None,
        risk_usd=Decimal(str(row.risk_usd)) if row.risk_usd is not None else None,
        trailing_peak_pnl_pct=Decimal(str(row.trailing_peak_pnl_pct)),
        cumulative_close_pct=Decimal(str(row.cumulative_close_pct)),
    )


def _domain_to_orm(pos: Position) -> PositionORM:
    return PositionORM(
        id=pos.id,
        symbol=pos.symbol,
        quantity=float(pos.quantity),
        entry_price=float(pos.entry_price),
        current_price=float(pos.current_price),
        liquidation_price=float(pos.liquidation_price),
        unrealized_pnl=float(pos.unrealized_pnl),
        leverage=pos.leverage,
        side=pos.side,
        profit_target=float(pos.profit_target) if pos.profit_target is not None else None,
        stop_loss=float(pos.stop_loss) if pos.stop_loss is not None else None,
        tp_order_id=pos.tp_order_id,
        sl_order_id=pos.sl_order_id,
        entry_order_id=pos.entry_order_id,
        opened_at=pos.opened_at,
        confidence=float(pos.confidence) if pos.confidence is not None else None,
        risk_usd=float(pos.risk_usd) if pos.risk_usd is not None else None,
        trailing_peak_pnl_pct=float(pos.trailing_peak_pnl_pct),
        cumulative_close_pct=float(pos.cumulative_close_pct),
    )


class PositionRepository:
    """CRUD operations for the positions table."""

    async def get(self, session: AsyncSession, position_id: int) -> Position | None:
        with_context(logger).debug("position_repository.get", position_id=position_id)
        result = await session.get(PositionORM, position_id)
        return _orm_to_domain(result) if result else None

    async def get_by_symbol(self, session: AsyncSession, symbol: str) -> Position | None:
        with_context(logger).debug("position_repository.get_by_symbol", symbol=symbol)
        stmt = select(PositionORM).where(PositionORM.symbol == symbol)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return _orm_to_domain(row) if row else None

    async def list_all(self, session: AsyncSession) -> list[Position]:
        with_context(logger).debug("position_repository.list_all")
        result = await session.execute(select(PositionORM))
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, position: Position) -> Position:
        with_context(logger).info("position_repository.create", symbol=position.symbol)
        row = _domain_to_orm(position)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def update(self, session: AsyncSession, position: Position) -> Position:
        if position.id is None:
            raise ValueError("Cannot update a Position without an id")
        with_context(logger).info("position_repository.update", position_id=position.id)
        row = await session.get(PositionORM, position.id)
        if row is None:
            raise ValueError(f"Position {position.id} not found")
        row.symbol = position.symbol
        row.quantity = float(position.quantity)
        row.entry_price = float(position.entry_price)
        row.current_price = float(position.current_price)
        row.liquidation_price = float(position.liquidation_price)
        row.unrealized_pnl = float(position.unrealized_pnl)
        row.leverage = position.leverage
        row.side = position.side
        row.profit_target = float(position.profit_target) if position.profit_target else None
        row.stop_loss = float(position.stop_loss) if position.stop_loss else None
        row.tp_order_id = position.tp_order_id
        row.sl_order_id = position.sl_order_id
        row.entry_order_id = position.entry_order_id
        row.opened_at = position.opened_at
        row.confidence = float(position.confidence) if position.confidence else None
        row.risk_usd = float(position.risk_usd) if position.risk_usd else None
        row.trailing_peak_pnl_pct = float(position.trailing_peak_pnl_pct)
        row.cumulative_close_pct = float(position.cumulative_close_pct)
        await session.flush()
        return _orm_to_domain(row)

    async def delete(self, session: AsyncSession, position_id: int) -> None:
        with_context(logger).info("position_repository.delete", position_id=position_id)
        row = await session.get(PositionORM, position_id)
        if row is not None:
            await session.delete(row)
            await session.flush()

    async def apply_three_way_state(
        self,
        session: AsyncSession,
        position_id: int,
        *,
        partial_close_pct: Decimal,
        stop_loss: Decimal | None,
        peak_pnl: Decimal,
    ) -> None:
        """Atomic UPDATE of three-way state contract fields in a single statement.

        Emits exactly ONE ``UPDATE ... WHERE id = :id`` covering
        (cumulative_close_pct, stop_loss, trailing_peak_pnl_pct) together so
        the 10-second stop-loss monitor cannot observe a torn write.
        No prior SELECT; no ORM instance loaded.
        """
        with_context(logger).info(
            "position_repository.apply_three_way_state",
            position_id=position_id,
            partial_close_pct=str(partial_close_pct),
            stop_loss=str(stop_loss),
            peak_pnl=str(peak_pnl),
        )
        stmt = (
            update(PositionORM)
            .where(PositionORM.id == position_id)
            .values(
                cumulative_close_pct=float(partial_close_pct),
                stop_loss=float(stop_loss) if stop_loss is not None else None,
                trailing_peak_pnl_pct=float(peak_pnl),
            )
        )
        await session.execute(stmt)
        await session.flush()
