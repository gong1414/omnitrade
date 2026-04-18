"""POST /api/v1/actions/close-position — password gate + dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)


async def _seed_position(api_app, symbol: str) -> None:  # type: ignore[no-untyped-def]
    repo = PositionRepository()
    open_session = api_app.state.test_session_factory
    session = await open_session()
    try:
        await repo.create(
            session,
            Position(
                symbol=symbol,
                quantity=Decimal("1"),
                entry_price=Decimal("100"),
                current_price=Decimal("100"),
                liquidation_price=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                leverage=5,
                side="long",
                entry_order_id=f"ord-{symbol}",
                opened_at=datetime(2026, 4, 18, tzinfo=UTC),
            ),
        )
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_close_rejects_wrong_password(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.post(
        "/api/v1/actions/close-position",
        json={"symbol": "BTC_USDT", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_close_accepts_correct_password(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed_position(api_app, "BTC_USDT")
    resp = await api_client.post(
        "/api/v1/actions/close-position",
        json={"symbol": "BTC_USDT", "password": "s3cret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == "close-1"

    # FakeExchange recorded a close at 100%.
    exchange = api_app.state.test_exchange
    assert exchange.close_calls[-1]["position_id"] == "BTC_USDT"
    assert exchange.close_calls[-1]["percentage"] == 100.0


@pytest.mark.asyncio
async def test_close_disabled_when_password_unset(monkeypatch, api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    # Null out the password on the cached settings.
    _ = api_app.state.api_container  # ensure container built
    import omnitrade.config as cfg

    cfg._settings.manual_close_password = None  # type: ignore[union-attr]
    resp = await api_client.post(
        "/api/v1/actions/close-position",
        json={"symbol": "BTC_USDT", "password": "anything"},
    )
    assert resp.status_code == 401
    assert "disabled" in resp.json()["detail"].lower()
