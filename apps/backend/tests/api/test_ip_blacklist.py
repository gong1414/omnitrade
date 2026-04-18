"""IPBlacklistMiddleware — 403 for listed IPs, passthrough otherwise."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from omnitrade.api.middleware import IPBlacklistMiddleware
from omnitrade.main import create_app


@pytest.mark.asyncio
async def test_blacklist_rejects_listed_ip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("IP_BLACKLIST", "1.2.3.4,5.6.7.8")
    # Rebuild app so the middleware picks up the env var.
    import omnitrade.config as cfg

    cfg._settings = None
    app = create_app()

    transport = ASGITransport(app=app, client=("1.2.3.4", 0))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"


@pytest.mark.asyncio
async def test_blacklist_allows_unlisted_ip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("IP_BLACKLIST", "1.2.3.4")
    import omnitrade.config as cfg

    cfg._settings = None
    app = create_app()

    transport = ASGITransport(app=app, client=("9.9.9.9", 0))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_blacklist_empty_env_lets_everything_through(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("IP_BLACKLIST", raising=False)
    mw = IPBlacklistMiddleware(app=lambda *_: None)  # type: ignore[arg-type]
    assert mw.blacklist == frozenset()
