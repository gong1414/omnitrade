"""Unit tests for news_data + external_data tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from omnitrade.agents.tools.external_data import build_external_data_tool
from omnitrade.agents.tools.news_data import build_news_data_tool
from omnitrade.infrastructure.news.news_fetcher import NewsItem


class _StubNewsFetcher:
    async def fetch(self) -> list[NewsItem]:
        base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        return [
            NewsItem(
                source="coindesk",
                headline=f"headline-{i}",
                summary=f"summary-{i}",
                published_at=base,
            )
            for i in range(5)
        ]


@pytest.mark.asyncio
async def test_news_tool_returns_limited_items() -> None:
    tool = build_news_data_tool(_StubNewsFetcher())  # type: ignore[arg-type]
    result = await tool.ainvoke(dict(limit=3))
    assert result["count"] == 3
    assert [it["headline"] for it in result["items"]] == [
        "headline-0",
        "headline-1",
        "headline-2",
    ]


@pytest.mark.asyncio
async def test_news_tool_default_limit_applies() -> None:
    tool = build_news_data_tool(_StubNewsFetcher())  # type: ignore[arg-type]
    result = await tool.ainvoke({})
    # stub returns 5; default limit is 10 -> no truncation
    assert result["count"] == 5


@pytest.mark.asyncio
async def test_external_data_tool_passes_endpoint_and_payload() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    async def fetcher(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        seen.append((endpoint, payload))
        return {"ok": True, "echo": payload}

    tool = build_external_data_tool(fetcher)
    result = await tool.ainvoke(dict(endpoint="onchain.eth_gas", payload={"window": "1h"}))
    assert result == {"ok": True, "echo": {"window": "1h"}}
    assert seen == [("onchain.eth_gas", {"window": "1h"})]


@pytest.mark.asyncio
async def test_external_data_tool_defaults_empty_payload() -> None:
    async def fetcher(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"endpoint": endpoint, "payload": payload}

    tool = build_external_data_tool(fetcher)
    result = await tool.ainvoke(dict(endpoint="ping"))
    assert result == {"endpoint": "ping", "payload": {}}
