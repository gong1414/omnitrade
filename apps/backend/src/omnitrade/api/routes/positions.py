"""GET /api/v1/positions — open futures positions (all or by symbol)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.api.deps import get_db_session, get_position_repository
from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)

router = APIRouter(tags=["positions"])


def _position_to_dict(pos: Position) -> dict[str, Any]:
    return {
        "id": pos.id,
        "symbol": pos.symbol,
        "side": pos.side,
        "quantity": str(pos.quantity),
        "entry_price": str(pos.entry_price),
        "current_price": str(pos.current_price),
        "leverage": pos.leverage,
        "unrealized_pnl": str(pos.unrealized_pnl),
        "stop_loss": str(pos.stop_loss) if pos.stop_loss is not None else None,
        "trailing_peak_pnl_pct": str(pos.trailing_peak_pnl_pct),
        "cumulative_close_pct": str(pos.cumulative_close_pct),
        "opened_at": pos.opened_at.isoformat(),
        "confidence": str(pos.confidence) if pos.confidence is not None else None,
    }


@router.get("/positions")
async def list_positions(
    repo: PositionRepository = Depends(get_position_repository),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """List all open positions. Filters out soft-closed (100%) entries."""
    rows = await repo.list_all(session)
    open_rows = [p for p in rows if p.cumulative_close_pct < Decimal(100)]
    return {
        "positions": [_position_to_dict(p) for p in open_rows],
        "count": len(open_rows),
    }


@router.get("/positions/{symbol}")
async def get_position(
    symbol: str,
    repo: PositionRepository = Depends(get_position_repository),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return a single position by symbol or 404 if absent."""
    pos = await repo.get_by_symbol(session, symbol)
    if pos is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"position {symbol!r} not found",
        )
    return _position_to_dict(pos)


__all__ = ["router"]
