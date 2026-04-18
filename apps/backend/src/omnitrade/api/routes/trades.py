"""GET /api/trades — paginated trade history (optional symbol filter)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.api.deps import get_db_session, get_trade_repository
from omnitrade.infrastructure.persistence.models import TradeORM
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository

router = APIRouter(tags=["trades"])


def _orm_to_dict(row: TradeORM) -> dict[str, Any]:
    pnl = Decimal(str(row.pnl)) if row.pnl is not None else None
    fee = Decimal(str(row.fee)) if row.fee is not None else None
    return {
        "id": row.id,
        "order_id": row.order_id,
        "symbol": row.symbol,
        "side": row.side,
        "type": row.type,
        "price": str(Decimal(str(row.price))),
        "quantity": str(Decimal(str(row.quantity))),
        "leverage": row.leverage,
        "pnl": str(pnl) if pnl is not None else None,
        "fee": str(fee) if fee is not None else None,
        "timestamp": row.timestamp.isoformat(),
        "status": row.status,
    }


@router.get("/trades")
async def list_trades(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    symbol: str | None = Query(default=None),
    repo: TradeRepository = Depends(get_trade_repository),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return trades, newest-first, with offset-based pagination.

    A ``symbol`` filter lets the frontend scope the dashboard trade pane to
    a single contract; omit to get every trade across all pairs.
    """
    count_stmt = select(func.count()).select_from(TradeORM)
    rows_stmt = select(TradeORM).order_by(TradeORM.timestamp.desc())

    if symbol:
        count_stmt = count_stmt.where(TradeORM.symbol == symbol)
        rows_stmt = rows_stmt.where(TradeORM.symbol == symbol)

    total = (await session.execute(count_stmt)).scalar_one()
    rows_stmt = rows_stmt.offset(offset).limit(limit)
    result = await session.execute(rows_stmt)
    orm_rows = list(result.scalars().all())
    _ = repo  # keep in dep graph for override/testing

    return {
        "trades": [_orm_to_dict(r) for r in orm_rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "symbol": symbol,
    }


__all__ = ["router"]
