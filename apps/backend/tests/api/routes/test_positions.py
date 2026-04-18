"""GET /api/v1/positions — list + detail + 404."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)


async def _seed_positions(api_app, *positions: Position) -> None:  # type: ignore[no-untyped-def]
    repo = PositionRepository()
    open_session = api_app.state.test_session_factory
    session = await open_session()
    try:
        for p in positions:
            await repo.create(session, p)
        await session.commit()
    finally:
        await session.close()


def _position(symbol: str = "BTC_USDT") -> Position:
    return Position(
        symbol=symbol,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("105"),
        liquidation_price=Decimal("0"),
        unrealized_pnl=Decimal("5"),
        leverage=5,
        side="long",
        entry_order_id=f"ord-{symbol}",
        opened_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_positions_list_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/positions")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"positions": [], "count": 0}


@pytest.mark.asyncio
async def test_positions_list_returns_open(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed_positions(api_app, _position("BTC_USDT"), _position("ETH_USDT"))
    resp = await api_client.get("/api/v1/positions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    symbols = {p["symbol"] for p in body["positions"]}
    assert symbols == {"BTC_USDT", "ETH_USDT"}


@pytest.mark.asyncio
async def test_position_detail_404(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/positions/MISSING")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_position_detail_found(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed_positions(api_app, _position("BTC_USDT"))
    resp = await api_client.get("/api/v1/positions/BTC_USDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTC_USDT"
    assert Decimal(body["trailing_peak_pnl_pct"]) == Decimal(0)
    assert Decimal(body["cumulative_close_pct"]) == Decimal(0)
