"""News-data tool — fetch normalized news headlines via the NewsFetcher adapter.

Returns a deterministic list (sorted newest-first in the adapter) so the
agent's prompt is stable across cycles with identical inputs.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.infrastructure.news.news_fetcher import NewsFetcher
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class FetchNewsArgs(BaseModel):
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of news items to return (newest first).",
    )


def build_news_data_tool(fetcher: NewsFetcher) -> StructuredTool:
    async def _fetch_news(limit: int = 10) -> dict[str, Any]:
        with_context(logger).info("tool.fetch_news", limit=limit)
        items = await fetcher.fetch()
        trimmed = items[:limit]
        return {
            "items": [
                {
                    "source": it.source,
                    "headline": it.headline,
                    "summary": it.summary,
                    "sentiment": it.sentiment,
                    "published_at": it.published_at.isoformat(),
                }
                for it in trimmed
            ],
            "count": len(trimmed),
        }

    return StructuredTool.from_function(
        coroutine=_fetch_news,
        name="fetch_news",
        description=(
            "Fetch normalized crypto news headlines (sorted newest-first). "
            "Use to enrich the think prompt with market-moving context."
        ),
        args_schema=FetchNewsArgs,
    )


__all__ = ["FetchNewsArgs", "build_news_data_tool"]
