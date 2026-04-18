"""GET /api/ready — DB + exchange ping; 503 on any failure."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ready_returns_200_when_both_checks_pass(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"db": "ok", "exchange": "ok"}


@pytest.mark.asyncio
async def test_ready_503_when_exchange_fails(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    exchange = api_app.state.test_exchange
    exchange._balance = None  # FakeExchange.fetch_balance raises when unset

    resp = await api_client.get("/api/ready")
    assert resp.status_code == 503
    body = resp.json()
    # FastAPI puts our dict under "detail".
    detail = body["detail"]
    assert detail["checks"]["db"] == "ok"
    assert detail["checks"]["exchange"] == "error"
    assert detail["status"] == "degraded"


@pytest.mark.asyncio
async def test_ready_503_when_db_fails(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    # Replace session_factory with one that yields a session whose execute() raises.
    from unittest.mock import AsyncMock, MagicMock

    broken_session = MagicMock()
    broken_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    broken_session.close = AsyncMock()
    api_app.state.api_container.session_factory = lambda: broken_session  # type: ignore[assignment]

    resp = await api_client.get("/api/ready")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["checks"]["db"] == "error"


@pytest.mark.asyncio
async def test_ready_not_ready_when_both_fail(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import AsyncMock, MagicMock

    exchange = api_app.state.test_exchange
    exchange._balance = None

    broken_session = MagicMock()
    broken_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    broken_session.close = AsyncMock()
    api_app.state.api_container.session_factory = lambda: broken_session  # type: ignore[assignment]

    resp = await api_client.get("/api/ready")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["status"] == "not_ready"
    assert detail["checks"] == {"db": "error", "exchange": "error"}
