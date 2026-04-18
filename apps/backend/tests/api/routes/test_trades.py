"""GET /api/trades — pagination + symbol filter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from omnitrade.domain.entities import Trade
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository


async def _seed_trades(api_app, *trades: Trade) -> None:  # type: ignore[no-untyped-def]
    repo = TradeRepository()
    open_session = api_app.state.test_session_factory
    session = await open_session()
    try:
        for t in trades:
            await repo.create(session, t)
        await session.commit()
    finally:
        await session.close()


def _trade(
    order_id: str,
    symbol: str = "BTC_USDT",
    offset_minutes: int = 0,
    pnl: str | None = None,
) -> Trade:
    return Trade(
        order_id=order_id,
        symbol=symbol,
        side="long",
        type="open",
        price=Decimal("100"),
        quantity=Decimal("1"),
        leverage=5,
        pnl=Decimal(pnl) if pnl is not None else None,
        fee=Decimal("0.1"),
        timestamp=datetime(2026, 4, 18, tzinfo=UTC) + timedelta(minutes=offset_minutes),
        status="filled",
    )


@pytest.mark.asyncio
async def test_trades_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/trades")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "trades": [],
        "total": 0,
        "limit": 100,
        "offset": 0,
        "symbol": None,
    }


@pytest.mark.asyncio
async def test_trades_paginate_newest_first(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed_trades(
        api_app,
        _trade("o-1", offset_minutes=0),
        _trade("o-2", offset_minutes=1),
        _trade("o-3", offset_minutes=2),
        _trade("o-4", offset_minutes=3),
    )

    resp = await api_client.get("/api/trades?limit=2&offset=0")
    body = resp.json()
    assert body["total"] == 4
    assert [t["order_id"] for t in body["trades"]] == ["o-4", "o-3"]

    resp = await api_client.get("/api/trades?limit=2&offset=2")
    body = resp.json()
    assert [t["order_id"] for t in body["trades"]] == ["o-2", "o-1"]


@pytest.mark.asyncio
async def test_trades_filter_by_symbol(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed_trades(
        api_app,
        _trade("o-1", symbol="BTC_USDT"),
        _trade("o-2", symbol="ETH_USDT"),
        _trade("o-3", symbol="ETH_USDT", offset_minutes=1),
    )

    resp = await api_client.get("/api/trades?symbol=ETH_USDT")
    body = resp.json()
    assert body["total"] == 2
    assert body["symbol"] == "ETH_USDT"
    assert {t["symbol"] for t in body["trades"]} == {"ETH_USDT"}


@pytest.mark.asyncio
async def test_trades_limit_bounds(api_client) -> None:  # type: ignore[no-untyped-def]
    assert (await api_client.get("/api/trades?limit=0")).status_code == 422
    assert (await api_client.get("/api/trades?limit=1000")).status_code == 422
