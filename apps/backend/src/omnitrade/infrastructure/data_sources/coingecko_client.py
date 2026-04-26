"""CoinGecko REST client — free tier, no API key required.

Provides: market cap, 24h volume, price change, circulating supply,
top gainers/losers, trending coins.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def get_market_overview(
        self, ids: list[str] | None = None, per_page: int = 20
    ) -> dict[str, Any]:
        """Fetch top coins by market cap with key metrics."""
        params: dict[str, Any] = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "1h,24h,7d",
        }
        if ids:
            params["ids"] = ",".join(ids)

        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get("/coins/markets", params=params)
            resp.raise_for_status()
            coins = resp.json()

        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "coins": [
                {
                    "id": c.get("id"),
                    "symbol": c.get("symbol", "").upper(),
                    "price_usd": c.get("current_price"),
                    "market_cap_usd": c.get("market_cap"),
                    "volume_24h_usd": c.get("total_volume"),
                    "change_1h_pct": c.get("price_change_percentage_1h_in_currency"),
                    "change_24h_pct": c.get("price_change_percentage_24h_in_currency"),
                    "change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
                    "high_24h": c.get("high_24h"),
                    "low_24h": c.get("low_24h"),
                    "ath_usd": c.get("ath"),
                    "ath_date": c.get("ath_date"),
                    "circulating_supply": c.get("circulating_supply"),
                }
                for c in coins
            ],
        }

    async def get_trending(self) -> dict[str, Any]:
        """Fetch trending coins (top-7 on CoinGecko in the last 24h)."""
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get("/search/trending")
            resp.raise_for_status()
            data = resp.json()

        coins = data.get("coins", [])
        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "trending": [
                {
                    "id": c.get("item", {}).get("id"),
                    "symbol": c.get("item", {}).get("symbol", "").upper(),
                    "market_cap_rank": c.get("item", {}).get("market_cap_rank"),
                    "score": c.get("item", {}).get("score"),
                    "price_btc": c.get("item", {}).get("price_btc"),
                }
                for c in coins[:10]
            ],
        }

    async def get_global(self) -> dict[str, Any]:
        """Fetch global crypto market data (total market cap, volume, BTC dominance)."""
        async with httpx.AsyncClient(timeout=self._timeout, base_url=_BASE_URL) as client:
            resp = await client.get("/global")
            resp.raise_for_status()
            data = resp.json().get("data", {})

        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "total_market_cap_usd": data.get("total_market_cap", {}).get("usd"),
            "total_volume_24h_usd": data.get("total_volume", {}).get("usd"),
            "btc_dominance_pct": data.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance_pct": data.get("market_cap_percentage", {}).get("eth"),
            "active_coins": data.get("active_cryptocurrencies"),
            "markets": data.get("markets"),
            "market_cap_change_24h_pct": data.get("market_cap_change_percentage_24h_usd"),
        }
