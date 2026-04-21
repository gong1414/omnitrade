"""Fear & Greed Index client — free API, no key required.

Provides: current + historical fear/greed sentiment score (0-100).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

_API_URL = "https://api.alternative.me/fng/"


class FearGreedClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def get(self, limit: int = 7) -> dict[str, Any]:
        """Fetch fear & greed index (current + history).

        Args:
            limit: Number of data points (1 = today only, max ~365).
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(_API_URL, params={"limit": limit, "format": "json"})
            resp.raise_for_status()
            data = resp.json()

        entries = []
        for item in data.get("data", []):
            ts = int(item.get("timestamp", 0))
            entries.append({
                "value": int(item.get("value", 0)),
                "classification": item.get("value_classification"),
                "timestamp": datetime.fromtimestamp(ts, tz=UTC).isoformat(),
            })

        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "current": entries[0] if entries else None,
            "history": entries[1:] if len(entries) > 1 else [],
        }
