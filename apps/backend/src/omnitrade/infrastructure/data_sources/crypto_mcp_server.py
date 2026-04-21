"""OmniTrade Crypto Data MCP Server — exposes crypto data sources as MCP tools.

Run as stdio MCP server:
    python -m omnitrade.infrastructure.data_sources.crypto_mcp_server

AnyTool discovers these tools via config_mcp.json and routes crypto-related
queries to them automatically through Smart Tool RAG.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omnitrade-crypto-data")


@mcp.tool()
async def coingecko_market_overview(
    coin_ids: str = "bitcoin,ethereum",
    per_page: int = 20,
) -> str:
    """Fetch top coins by market cap with prices, 24h changes, market cap, volume.

    Args:
        coin_ids: Comma-separated CoinGecko coin IDs (e.g. "bitcoin,ethereum").
        per_page: Number of coins to return.
    """
    from omnitrade.infrastructure.data_sources.coingecko_client import CoinGeckoClient

    client = CoinGeckoClient()
    data = await client.get_market_overview(ids=coin_ids.split(","), per_page=per_page)
    return json.dumps(data, default=str)


@mcp.tool()
async def coingecko_trending() -> str:
    """Fetch trending coins on CoinGecko (top-7 trending in the last 24h)."""
    from omnitrade.infrastructure.data_sources.coingecko_client import CoinGeckoClient

    client = CoinGeckoClient()
    data = await client.get_trending()
    return json.dumps(data, default=str)


@mcp.tool()
async def coingecko_global() -> str:
    """Fetch global crypto market data: total market cap, volume, BTC dominance."""
    from omnitrade.infrastructure.data_sources.coingecko_client import CoinGeckoClient

    client = CoinGeckoClient()
    data = await client.get_global()
    return json.dumps(data, default=str)


@mcp.tool()
async def fear_greed_index(days: int = 7) -> str:
    """Fetch the Crypto Fear & Greed Index (0=Extreme Fear, 100=Extreme Greed).

    Args:
        days: Number of days of history (1=today only, max ~365).
    """
    from omnitrade.infrastructure.data_sources.fear_greed_client import FearGreedClient

    client = FearGreedClient()
    data = await client.get(limit=days)
    return json.dumps(data, default=str)


@mcp.tool()
async def coinglass_derivatives(symbol: str = "BTC") -> str:
    """Fetch derivatives data: funding rates, open interest, long/short ratios.

    Requires COINGLASS_API_KEY environment variable.

    Args:
        symbol: Trading symbol (e.g. "BTC", "ETH").
    """
    api_key = os.environ.get("COINGLASS_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "COINGLASS_API_KEY not set"})

    from omnitrade.infrastructure.data_sources.coinglass_client import CoinglassClient

    client = CoinglassClient(api_key=api_key)
    data = await client.get_derivatives_overview(symbol=symbol)
    return json.dumps(data, default=str)


@mcp.tool()
async def whale_transactions(
    min_value_usd: int = 500_000,
    limit: int = 20,
) -> str:
    """Track large crypto transactions (whale movements) on-chain.

    Requires WHALE_ALERT_API_KEY environment variable.

    Args:
        min_value_usd: Minimum transaction value in USD (default 500k).
        limit: Maximum number of transactions (1-100).
    """
    api_key = os.environ.get("WHALE_ALERT_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "WHALE_ALERT_API_KEY not set"})

    from omnitrade.infrastructure.data_sources.whale_alert_client import WhaleAlertClient

    client = WhaleAlertClient(api_key=api_key)
    data = await client.get_transactions(min_value_usd=min_value_usd, limit=limit)
    return json.dumps(data, default=str)


if __name__ == "__main__":
    mcp.run(transport="stdio")
