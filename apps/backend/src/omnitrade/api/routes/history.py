"""GET /api/history — account-equity time series (24h / 7d / 30d).

Reads from ``account_history`` via :class:`AccountHistoryRepository` and
flips the list into parallel-array form so the dashboard's Recharts
line chart can consume it without per-row reshape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.api.deps import get_account_history_repository, get_db_session
from omnitrade.infrastructure.persistence.models import AccountHistoryORM
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)

router = APIRouter(tags=["history"])

Window = Literal["24h", "7d", "30d"]

_WINDOW_TO_DELTA: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("/history")
async def get_history(
    window: Window = Query(default="24h"),
    repo: AccountHistoryRepository = Depends(get_account_history_repository),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Return the equity curve for the requested window.

    Response shape is parallel arrays (timestamps, total_value, …) which
    maps 1:1 to ``Recharts <LineChart data=[{ts,v}]>`` after a zip on the
    frontend. Ordering is chronological (oldest → newest).
    """
    # Delegate to the repository for the raw query so we stay pattern-aligned
    # with ``account_service.list_recent``; we filter by cutoff here since no
    # repo method exposes a window filter yet.
    delta = _WINDOW_TO_DELTA[window]
    cutoff = datetime.now(tz=UTC) - delta

    stmt = (
        select(AccountHistoryORM)
        .where(AccountHistoryORM.timestamp >= cutoff)
        .order_by(AccountHistoryORM.timestamp.asc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    # Keep repository in the dependency graph for future reuse (and for
    # tests that override it).
    _ = repo

    timestamps = [row.timestamp.isoformat() for row in rows]
    total_value = [float(row.total_value) for row in rows]
    unrealized_pnl = [float(row.unrealized_pnl) for row in rows]
    realized_pnl = [float(row.realized_pnl) for row in rows]
    return_percent = [float(row.return_percent) for row in rows]

    return {
        "window": window,
        "count": len(rows),
        "timestamps": timestamps,
        "total_value": total_value,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "return_percent": return_percent,
    }


__all__ = ["router"]
