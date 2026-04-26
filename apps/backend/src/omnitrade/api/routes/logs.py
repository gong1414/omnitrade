"""GET /api/logs — recent structlog events from the in-process LogBuffer.

The buffer is populated by the ``buffer_processor`` installed during
``configure_structlog`` (see ``omnitrade.main.lifespan``); this endpoint
tails it newest-first with an optional ``level`` filter.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from omnitrade.api.deps import get_log_buffer
from omnitrade.observability.log_store import LogBuffer

router = APIRouter(tags=["logs"])

# Upper-case preferred externally (HTTP-friendly); lower-case matches
# structlog's internal ``add_log_level``. Accept both.
Level = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@router.get("/logs")
async def list_logs(
    level: Level | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    buffer: LogBuffer = Depends(get_log_buffer),
) -> dict[str, Any]:
    """Return up to ``limit`` recent events at or above ``level``."""
    rows = buffer.tail(level=level.lower() if level else None, limit=limit)
    # Normalise to a stable shape for the dashboard.
    events = [
        {
            "level": evt.get("level", "info"),
            "timestamp": evt.get("timestamp"),
            "message": evt.get("event"),
            "context": {k: v for k, v in evt.items() if k not in {"level", "timestamp", "event"}},
        }
        for evt in rows
    ]
    return {"events": events, "count": len(events), "level": level, "limit": limit}


__all__ = ["router"]
