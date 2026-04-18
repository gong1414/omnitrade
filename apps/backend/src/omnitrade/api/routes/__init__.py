"""Phase-5 FastAPI route aggregator.

Phase-5 routes are mounted under ``/api/v1``. Phase 8.3 adds a second
router aggregator for the upstream-parity REST surface at ``/api`` —
``history``, ``trades``, ``logs``, ``stats``, ``prices``, ``strategy``,
``health``, ``ready``. Each sub-module owns its own ``APIRouter`` so
tests can include a single router in isolation.
"""

from __future__ import annotations

from fastapi import APIRouter

from omnitrade.api.routes import (
    account,
    actions,
    config,
    decisions,
    health,
    history,
    logs,
    positions,
    prices,
    ready,
    rebate,
    stats,
    strategy,
    trades,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(account.router)
api_router.include_router(positions.router)
api_router.include_router(decisions.router)
api_router.include_router(config.router)
api_router.include_router(actions.router)
api_router.include_router(rebate.router)


# Phase 8.3: upstream-parity REST routes live at ``/api/...`` (no v1 prefix).
api_v8_router = APIRouter(prefix="/api")
api_v8_router.include_router(history.router)
api_v8_router.include_router(trades.router)
api_v8_router.include_router(logs.router)
api_v8_router.include_router(stats.router)
api_v8_router.include_router(prices.router)
api_v8_router.include_router(strategy.router)
api_v8_router.include_router(health.router)
api_v8_router.include_router(ready.router)


__all__ = ["api_router", "api_v8_router"]
