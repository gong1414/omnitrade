"""TradeRepository — CRUD for the trades table."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import Trade
from omnitrade.infrastructure.persistence.models import TradeORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: TradeORM) -> Trade:
    return Trade(
        id=row.id,
        order_id=row.order_id,
        symbol=row.symbol,
        side=row.side,
        type=row.type,
        price=Decimal(str(row.price)),
        quantity=Decimal(str(row.quantity)),
        leverage=row.leverage,
        pnl=Decimal(str(row.pnl)) if row.pnl is not None else None,
        fee=Decimal(str(row.fee)) if row.fee is not None else None,
        timestamp=row.timestamp,
        status=row.status,
    )


def _domain_to_orm(trade: Trade) -> TradeORM:
    return TradeORM(
        id=trade.id,
        order_id=trade.order_id,
        symbol=trade.symbol,
        side=trade.side,
        type=trade.type,
        price=float(trade.price),
        quantity=float(trade.quantity),
        leverage=trade.leverage,
        pnl=float(trade.pnl) if trade.pnl is not None else None,
        fee=float(trade.fee) if trade.fee is not None else None,
        timestamp=trade.timestamp,
        status=trade.status,
    )


class TradeRepository:
    """CRUD operations for the trades table."""

    async def get(self, session: AsyncSession, trade_id: int) -> Trade | None:
        with_context(logger).debug("trade_repository.get", trade_id=trade_id)
        result = await session.get(TradeORM, trade_id)
        return _orm_to_domain(result) if result else None

    async def list_by_symbol(self, session: AsyncSession, symbol: str) -> list[Trade]:
        with_context(logger).debug("trade_repository.list_by_symbol", symbol=symbol)
        stmt = select(TradeORM).where(TradeORM.symbol == symbol).order_by(TradeORM.timestamp)
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def list_all(self, session: AsyncSession) -> list[Trade]:
        with_context(logger).debug("trade_repository.list_all")
        result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp))
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, trade: Trade) -> Trade:
        with_context(logger).info("trade_repository.create", symbol=trade.symbol)
        row = _domain_to_orm(trade)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def realized_pnl_since(self, session: AsyncSession, since_utc: datetime) -> Decimal:
        """Sum realized ``pnl`` of closed trades with ``timestamp >= since_utc``.

        Realized PnL lives on the ``trades`` table's ``pnl`` column and is
        only populated for closing trades (``type='close'``). Opens carry
        ``pnl=NULL`` so a naive SUM would be fine — we filter on ``close``
        explicitly for clarity and to stay correct if future migrations
        start populating ``pnl`` on opens.

        Returns ``Decimal(0)`` when no matching rows exist.
        """
        with_context(logger).debug(
            "trade_repository.realized_pnl_since", since_utc=since_utc.isoformat()
        )
        stmt = select(func.coalesce(func.sum(TradeORM.pnl), 0.0)).where(
            TradeORM.timestamp >= since_utc,
            TradeORM.type == "close",
        )
        result = await session.execute(stmt)
        total = result.scalar_one()
        return Decimal(str(total))
