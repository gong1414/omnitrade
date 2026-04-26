"""Whale Alert client — large crypto transaction monitoring.

Requires WHALE_ALERT_API_KEY. Free tier: 10 requests/min.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.whale-alert.io/v1"


class WhaleAlertClient:
    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def get_transactions(
        self,
        min_value_usd: int = 500_000,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Fetch recent large transactions above min_value_usd.

        Args:
            min_value_usd: Minimum transaction value in USD (default 500k).
            limit: Max transactions to return (1-100).
        """
        start = int(datetime.now(tz=UTC).timestamp()) - 3600  # last hour
        params = {
            "api_key": self._api_key,
            "min_value": min_value_usd,
            "start": start,
            "limit": limit,
        }

        with_context(logger).info("whale_alert.fetch", min_value_usd=min_value_usd)
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get("/transactions", params=params)
            resp.raise_for_status()
            data = resp.json()

        txs = []
        for tx in data.get("transactions", []):
            txs.append(
                {
                    "hash": tx.get("hash"),
                    "blockchain": tx.get("blockchain"),
                    "symbol": tx.get("symbol", "").upper(),
                    "amount": tx.get("amount"),
                    "amount_usd": tx.get("amount_usd"),
                    "from_type": tx.get("from", {}).get("owner_type"),
                    "to_type": tx.get("to", {}).get("owner_type"),
                    "timestamp": datetime.fromtimestamp(tx.get("timestamp", 0), tz=UTC).isoformat(),
                }
            )

        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "count": len(txs),
            "transactions": txs,
        }
