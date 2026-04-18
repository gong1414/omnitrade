"""GET /api/history — window filter + chronological ordering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from omnitrade.domain.entities import AccountSnapshot
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)


async def _seed_history(api_app, *snapshots: AccountSnapshot) -> None:  # type: ignore[no-untyped-def]
    repo = AccountHistoryRepository()
    open_session = api_app.state.test_session_factory
    session = await open_session()
    try:
        for s in snapshots:
            await repo.create(session, s)
        await session.commit()
    finally:
        await session.close()


def _snap(at: datetime, total: str = "1000") -> AccountSnapshot:
    return AccountSnapshot(
        timestamp=at,
        total_value=Decimal(total),
        available_cash=Decimal("500"),
        unrealized_pnl=Decimal("10"),
        realized_pnl=Decimal("5"),
        return_percent=Decimal("1.2"),
    )


@pytest.mark.asyncio
async def test_history_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "24h"
    assert body["count"] == 0
    assert body["timestamps"] == []
    assert body["total_value"] == []


@pytest.mark.asyncio
async def test_history_24h_returns_recent(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(tz=UTC)
    await _seed_history(
        api_app,
        _snap(now - timedelta(hours=1), "1001"),
        _snap(now - timedelta(hours=12), "1002"),
        _snap(now - timedelta(days=2), "999"),  # outside 24h window
    )

    resp = await api_client.get("/api/history?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # Chronological (oldest first): 12h-ago then 1h-ago.
    assert body["total_value"] == [1002.0, 1001.0]


@pytest.mark.asyncio
async def test_history_window_7d(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(tz=UTC)
    await _seed_history(
        api_app,
        _snap(now - timedelta(days=3), "1100"),
        _snap(now - timedelta(days=8), "1000"),  # outside 7d
    )

    resp = await api_client.get("/api/history?window=7d")
    body = resp.json()
    assert body["count"] == 1
    assert body["total_value"] == [1100.0]


@pytest.mark.asyncio
async def test_history_invalid_window_422(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/history?window=1y")
    assert resp.status_code == 422
