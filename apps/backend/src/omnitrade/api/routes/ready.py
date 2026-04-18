"""GET /api/ready — readiness probe (DB + exchange ping).

Returns 200 when both DB (``SELECT 1``) and exchange (``fetch_balance``)
respond; otherwise returns 503 with a ``checks`` breakdown so the
dashboard can surface which dependency degraded.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.api.deps import get_db_session, get_exchange
from omnitrade.domain.protocols import ExchangeClient

router = APIRouter(tags=["platform"])


async def _check_db(session: AsyncSession) -> str:
    """Run a trivial ``SELECT 1`` ping; return ``"ok"`` or ``"error"``."""
    try:
        result = await session.execute(text("SELECT 1"))
        row = result.scalar_one_or_none()
        return "ok" if row == 1 else "error"
    except Exception:
        return "error"


async def _check_exchange(exchange: ExchangeClient) -> str:
    """Probe the exchange via ``fetch_balance``; return ``"ok"`` or ``"error"``."""
    try:
        await exchange.fetch_balance()
        return "ok"
    except Exception:
        return "error"


@router.get("/ready")
async def get_ready(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    exchange: ExchangeClient = Depends(get_exchange),
) -> dict[str, Any]:
    """Aggregate DB + exchange pings. 503 on any failure."""
    db_status = await _check_db(session)
    exchange_status = await _check_exchange(exchange)

    checks = {"db": db_status, "exchange": exchange_status}
    if db_status == "ok" and exchange_status == "ok":
        return {"status": "ready", "checks": checks}

    # Partial failure — downgrade to 503 so orchestrators back-off.
    degraded = db_status == "ok" or exchange_status == "ok"
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "degraded" if degraded else "not_ready",
            "checks": checks,
        },
    )


__all__ = ["router"]
