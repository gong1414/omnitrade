"""GET /api/strategy — non-secret strategy configuration snapshot.

A trimmed view of ``Settings`` scoped to strategy-relevant fields; the
existing ``/api/v1/config`` endpoint already ships the full allow-list,
this one is the upstream-shaped view the dashboard header expects.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from omnitrade.config import Settings, get_settings

router = APIRouter(tags=["strategy"])


@router.get("/strategy")
async def get_strategy(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the strategy config used by the trading loop."""
    return {
        "name": settings.trading_strategy,
        "interval_minutes": settings.trading_interval_minutes,
        "max_leverage": settings.max_leverage,
        "max_positions": settings.max_positions,
        "max_holding_hours": settings.max_holding_hours,
        "extreme_stop_loss_percent": settings.extreme_stop_loss_percent,
        "initial_balance_usdt": settings.initial_balance_usdt,
        "multi_agent_enabled": settings.multi_agent_enabled,
    }


__all__ = ["router"]
