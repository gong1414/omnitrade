"""News fetcher tests — vcrpy cassette + normalization tests.

Uses httpx mocking to avoid live network calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from omnitrade.infrastructure.news.news_fetcher import NewsFetcher, NewsItem

# ── Normalization unit tests ───────────────────────────────────────────────


def _fetcher() -> NewsFetcher:
    return NewsFetcher(mcp_url="https://api.gatemcp.ai/mcp/news", timeout=5.0)


def test_normalize_list_response() -> None:
    fetcher = _fetcher()
    raw = [
        {
            "source": "CoinDesk",
            "headline": "BTC hits 65k",
            "summary": "Bitcoin reaches new high",
            "published_at": "2026-04-17T10:00:00Z",
            "sentiment": "positive",
        }
    ]
    items = fetcher._normalize(raw)
    assert len(items) == 1
    assert items[0].source == "CoinDesk"
    assert items[0].headline == "BTC hits 65k"
    assert items[0].sentiment == "positive"
    assert items[0].published_at.tzinfo is not None


def test_normalize_dict_with_items_key() -> None:
    fetcher = _fetcher()
    raw = {
        "items": [
            {"source": "Cointelegraph", "headline": "ETH upgrade", "published_at": 1713350400}
        ]
    }
    items = fetcher._normalize(raw)
    assert len(items) == 1
    assert items[0].source == "Cointelegraph"


def test_normalize_dict_with_data_key() -> None:
    fetcher = _fetcher()
    raw = {
        "data": [
            {"provider": "Reuters", "title": "Crypto news", "date": "2026-04-17T09:00:00+00:00"}
        ]
    }
    items = fetcher._normalize(raw)
    assert len(items) == 1
    assert items[0].source == "Reuters"
    assert items[0].headline == "Crypto news"


def test_normalize_empty_list() -> None:
    fetcher = _fetcher()
    items = fetcher._normalize([])
    assert items == []


def test_normalize_skips_non_dict_items() -> None:
    fetcher = _fetcher()
    items = fetcher._normalize(["not a dict", 42, None])
    assert items == []


def test_parse_dt_unix_seconds() -> None:
    fetcher = _fetcher()
    dt = fetcher._parse_dt(1713350400)
    assert dt.tzinfo is not None
    assert dt.year == 2024


def test_parse_dt_unix_millis() -> None:
    fetcher = _fetcher()
    dt = fetcher._parse_dt(1713350400000)  # ms timestamp
    assert dt.tzinfo is not None
    assert dt.year == 2024


def test_parse_dt_iso_string() -> None:
    fetcher = _fetcher()
    dt = fetcher._parse_dt("2026-04-17T10:00:00Z")
    assert dt.year == 2026
    assert dt.tzinfo is not None


def test_parse_dt_datetime_passthrough() -> None:
    fetcher = _fetcher()
    now = datetime.now(tz=UTC)
    dt = fetcher._parse_dt(now)
    assert dt == now


def test_parse_dt_none_returns_now() -> None:
    fetcher = _fetcher()
    dt = fetcher._parse_dt(None)
    assert dt.tzinfo is not None


def test_sort_newest_first() -> None:
    fetcher = _fetcher()
    raw = [
        {"source": "A", "headline": "old", "published_at": "2026-04-16T00:00:00Z"},
        {"source": "B", "headline": "new", "published_at": "2026-04-17T00:00:00Z"},
    ]
    items = fetcher._normalize(raw)
    assert items[0].headline == "new"
    assert items[1].headline == "old"


# ── HTTP fetch mock tests ──────────────────────────────────────────────────


async def test_fetch_success() -> None:
    """fetch() returns normalized NewsItem list on 200 response."""
    fetcher = _fetcher()
    sample_response = [
        {
            "source": "CoinDesk",
            "headline": "BTC surges",
            "summary": "Bitcoin up 5%",
            "published_at": "2026-04-17T12:00:00Z",
        }
    ]
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=sample_response)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("omnitrade.infrastructure.news.news_fetcher.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = mock_client
        items = await fetcher.fetch()

    assert len(items) == 1
    assert items[0].headline == "BTC surges"


async def test_fetch_http_error_propagates() -> None:
    """HTTPStatusError must NOT be swallowed."""
    fetcher = _fetcher()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("omnitrade.infrastructure.news.news_fetcher.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = mock_client
        with pytest.raises(httpx.HTTPStatusError):
            await fetcher.fetch()


async def test_fetch_timeout_propagates() -> None:
    """TimeoutException must NOT be swallowed."""
    fetcher = _fetcher()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("omnitrade.infrastructure.news.news_fetcher.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = mock_client
        with pytest.raises(httpx.TimeoutException):
            await fetcher.fetch()


def test_news_item_repr() -> None:
    item = NewsItem(
        source="Test",
        headline="A" * 50,
        summary="summary",
        published_at=datetime.now(tz=UTC),
    )
    r = repr(item)
    assert "Test" in r
