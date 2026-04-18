"""GET /api/health — liveness only, no DB / exchange calls."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_health_does_not_touch_db(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    """Liveness MUST NOT open a session or fetch from the exchange.

    We verify by swapping the container's session_factory with one that
    blows up on call; if /api/health hits it, the test fails.
    """

    def _explode() -> None:
        raise RuntimeError("health should not open a DB session")

    api_app.state.api_container.session_factory = _explode  # type: ignore[assignment]
    # Same for exchange — any call would error.
    exchange = api_app.state.test_exchange
    exchange._balance = None  # force fetch_balance to raise if called

    resp = await api_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
