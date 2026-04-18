"""NewsFetcher — wraps the Gate MCP news tool URL via httpx.

Returns normalized NewsItem list. No LLM involved.
Tests use vcrpy cassettes under tests/infrastructure/news/cassettes/.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class NewsItem:
    """Normalized news item from the Gate MCP news endpoint."""

    __slots__ = ("headline", "published_at", "raw", "sentiment", "source", "summary")

    def __init__(
        self,
        source: str,
        headline: str,
        summary: str,
        published_at: datetime,
        sentiment: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.source = source
        self.headline = headline
        self.summary = summary
        self.published_at = published_at
        self.sentiment = sentiment
        self.raw = raw or {}

    def __repr__(self) -> str:
        return f"NewsItem(source={self.source!r}, headline={self.headline[:40]!r})"


class NewsFetcher:
    """Fetch and normalize news from the Gate MCP news endpoint.

    Args:
        mcp_url: Full URL of the Gate MCP news endpoint.
        timeout: HTTP request timeout in seconds (default 10).
    """

    def __init__(self, mcp_url: str, timeout: float = 10.0) -> None:
        self._mcp_url = mcp_url
        self._timeout = timeout

    async def fetch(self) -> list[NewsItem]:
        """Fetch news items from the MCP endpoint.

        Returns:
            Normalized list of NewsItem (newest first).

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx responses (not swallowed).
            httpx.TimeoutException: on timeout (not swallowed).
        """
        with_context(logger).info("news_fetcher.fetch", url=self._mcp_url)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(self._mcp_url)
            response.raise_for_status()
            data = response.json()

        items = self._normalize(data)
        with_context(logger).info("news_fetcher.fetch_complete", count=len(items))
        return items

    def _normalize(self, data: Any) -> list[NewsItem]:
        """Normalize raw API response to NewsItem list.

        Handles both list and dict-with-items response shapes.
        """
        raw_items: list[Any] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            # Try common wrapper keys
            for key in ("items", "data", "news", "results"):
                if isinstance(data.get(key), list):
                    raw_items = data[key]
                    break
            if not raw_items and isinstance(data.get("content"), list):
                raw_items = data["content"]

        results: list[NewsItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or item.get("provider") or "unknown")
            headline = str(item.get("headline") or item.get("title") or item.get("text") or "")
            summary = str(item.get("summary") or item.get("description") or headline)
            sentiment = item.get("sentiment") or item.get("sentiment_label")

            published_raw = (
                item.get("published_at")
                or item.get("publishedAt")
                or item.get("date")
                or item.get("timestamp")
            )
            published_at = self._parse_dt(published_raw)

            results.append(
                NewsItem(
                    source=source,
                    headline=headline,
                    summary=summary,
                    published_at=published_at,
                    sentiment=str(sentiment) if sentiment else None,
                    raw=item,
                )
            )

        # Sort newest first
        results.sort(key=lambda x: x.published_at, reverse=True)
        return results

    @staticmethod
    def _parse_dt(raw: Any) -> datetime:
        """Parse a timestamp into a tz-aware datetime."""
        if raw is None:
            return datetime.now(tz=UTC)
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        if isinstance(raw, (int, float)):
            # Unix timestamp (seconds or ms)
            ts = float(raw)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=UTC)
        if isinstance(raw, str):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(tz=UTC)
