"""POST /api/v1/cycle/trigger — manually invoke one trading cycle.

The endpoint is the ops-only "fire now" button. It:

  * Refuses (503) when the scheduler was not wired (either
    ``SCHEDULER_ENABLED=false`` at startup or the ``trading_monitor`` build
    failed).
  * Refuses (409) if another manual trigger is already running — the
    monitor's own ``max_instances=1`` prevents the APScheduler from
    overlapping runs, but a manual retry from the UI shouldn't stack.
  * Caps runtime at 60s so a hung upstream LLM / exchange doesn't pin a
    worker forever.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["cycle"])

_lock = asyncio.Lock()


@router.post("/cycle/trigger")
async def trigger_cycle(request: Request) -> dict[str, Any]:
    """Force one cycle right now. 60s timeout. Returns elapsed time."""
    monitor = getattr(request.app.state, "trading_monitor", None)
    if monitor is None:
        raise HTTPException(
            503,
            "trading_monitor not wired (SCHEDULER_ENABLED=false or build failed)",
        )
    if _lock.locked():
        raise HTTPException(409, "another cycle is already running")
    async with _lock:
        t0 = datetime.now(UTC)
        try:
            await asyncio.wait_for(monitor.tick(), timeout=60.0)
        except TimeoutError as exc:
            raise HTTPException(504, "cycle exceeded 60s timeout") from exc
        elapsed = (datetime.now(UTC) - t0).total_seconds()
    return {"status": "ok", "elapsed_seconds": elapsed}


__all__ = ["router"]
