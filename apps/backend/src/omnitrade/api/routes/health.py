"""GET /api/health — liveness probe.

Phase 8.3 split: ``/api/health`` MUST be a pure-Python liveness check —
no DB round-trip, no exchange ping, no container lookup. The target is
p95 < 50 ms so Kubernetes / docker-compose can restart a hung process
without the liveness call itself being the hang.

See ``ready.py`` for the readiness probe (DB + exchange ping, <500 ms).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["platform"])

# Process start wall-clock — stamped at import so each worker reports its
# own uptime. ``time.monotonic()`` keeps the math immune to clock skew.
_PROCESS_START_MONOTONIC = time.monotonic()


@router.get("/health")
async def get_health() -> dict[str, Any]:
    """Return a liveness snapshot. Never touches DB / exchange.

    Shape mirrors upstream dashboard expectations: ``status``, ``version``,
    ``uptime_seconds``.
    """
    uptime = time.monotonic() - _PROCESS_START_MONOTONIC
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": round(uptime, 3),
    }


__all__ = ["router"]
