"""Coinglass API client — derivatives data (OI, funding, long/short ratio).

Requires COINGLASS_API_KEY. Free tier: limited requests/min.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

_BASE_URL = "https://open-api.coinglass.com"


class CoinglassClient:
    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"coinglass-api-key": self._api_key, "accept": "application/json"}

    async def get_funding_rates(self, symbol: str = "BTC") -> dict[str, Any]:
        """Fetch current funding rates across exchanges."""
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get(
                "/public/v2/funding",
                params={"symbol": symbol.upper(), "time_type": "all"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        rates = []
        for item in data.get("data", []):
            rates.append({
                "exchange": item.get("exchange"),
                "symbol": item.get("symbol"),
                "rate": item.get("rate"),
                "next_funding_time": item.get("nextFundingTime"),
            })
        return {"timestamp": datetime.now(tz=UTC).isoformat(), "funding_rates": rates}

    async def get_open_interest(self, symbol: str = "BTC") -> dict[str, Any]:
        """Fetch open interest across exchanges."""
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get(
                "/public/v2/openInterest",
                params={"symbol": symbol.upper(), "time_type": "all"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        oi_list = []
        for item in data.get("data", []):
            oi_list.append({
                "exchange": item.get("exchange"),
                "symbol": item.get("symbol"),
                "open_interest": item.get("openInterest"),
                "change_pct": item.get("change"),
            })
        return {"timestamp": datetime.now(tz=UTC).isoformat(), "open_interest": oi_list}

    async def get_long_short_ratio(self, symbol: str = "BTC") -> dict[str, Any]:
        """Fetch long/short ratio across exchanges."""
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get(
                "/public/v2/longShort",
                params={"symbol": symbol.upper(), "time_type": "all"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        ratios = []
        for item in data.get("data", []):
            ratios.append({
                "exchange": item.get("exchange"),
                "long_pct": item.get("longRatio"),
                "short_pct": item.get("shortRatio"),
                "long_short_ratio": item.get("longShortRatio"),
            })
        return {"timestamp": datetime.now(tz=UTC).isoformat(), "long_short_ratios": ratios}

    async def get_derivatives_overview(self, symbol: str = "BTC") -> dict[str, Any]:
        """Aggregate funding + OI + long/short into one payload."""
        funding = await self.get_funding_rates(symbol)
        oi = await self.get_open_interest(symbol)
        ls = await self.get_long_short_ratio(symbol)
        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "symbol": symbol.upper(),
            "funding_rates": funding.get("funding_rates", []),
            "open_interest": oi.get("open_interest", []),
            "long_short_ratios": ls.get("long_short_ratios", []),
        }
