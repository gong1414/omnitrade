"""GET /api/stats — Sharpe / drawdown / return / win-rate summary.

Per Phase 8.3 plan (MINOR-8 resolution) Sharpe MUST be computed from
``account_history.total_value`` log-returns — **not** ``trades.pnl`` — so
the number reflects actual portfolio volatility instead of per-order
noise. Win-rate is still computed from ``trades.pnl > 0`` because that
is the upstream definition.

ADR-H follow-up: document the switch and the math.
"""

from __future__ import annotations

import math
from decimal import Decimal
from itertools import pairwise
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.api.deps import get_db_session
from omnitrade.infrastructure.persistence.models import AccountHistoryORM, TradeORM

router = APIRouter(tags=["stats"])


def _sharpe_from_log_returns(values: list[float]) -> float:
    """Annualised Sharpe from a consecutive ``total_value`` series.

    * No ``risk_free_rate`` term — treat as 0 (upstream parity).
    * Annualisation factor = sqrt(252) (trading-day convention).
    * Returns 0.0 when we have fewer than 2 valid samples or zero volatility.
    """
    if len(values) < 2:
        return 0.0
    log_returns: list[float] = []
    for prev, curr in pairwise(values):
        if prev <= 0 or curr <= 0:
            continue
        log_returns.append(math.log(curr / prev))
    if len(log_returns) < 2:
        return 0.0
    n = len(log_returns)
    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
    stdev = math.sqrt(variance)
    if stdev == 0.0:
        return 0.0
    return (mean / stdev) * math.sqrt(252)


def _max_drawdown(values: list[float]) -> float:
    """Return the max peak-to-trough drawdown as a negative fraction.

    Example: a series going 100 → 80 returns ``-0.20``.
    """
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < worst:
                worst = dd
    return worst


def _total_return_percent(values: list[float]) -> float:
    """Simple first-to-last percent return."""
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return (values[-1] - values[0]) / values[0] * 100.0


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Portfolio summary statistics for the dashboard header row."""
    history_stmt = (
        select(AccountHistoryORM.total_value)
        .order_by(AccountHistoryORM.timestamp.asc())
    )
    history_rows = (await session.execute(history_stmt)).scalars().all()
    values = [float(v) for v in history_rows]

    sharpe = _sharpe_from_log_returns(values)
    mdd = _max_drawdown(values)
    ret = _total_return_percent(values)

    trades_stmt = select(TradeORM.pnl).where(TradeORM.pnl.is_not(None))
    pnl_rows = (await session.execute(trades_stmt)).scalars().all()
    pnls = [Decimal(str(v)) for v in pnl_rows]
    n_trades = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    win_rate = (wins / n_trades) if n_trades > 0 else 0.0

    return {
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "total_return_percent": ret,
        "win_rate": win_rate,
        "n_trades": n_trades,
    }


__all__ = ["router"]
