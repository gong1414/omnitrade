"""GET /api/logs — LogBuffer tail with level filter."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_logs_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"events": [], "count": 0, "level": None, "limit": 200}


@pytest.mark.asyncio
async def test_logs_tail_returns_newest_first(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    buf = api_app.state.api_container.log_buffer
    buf.append({"event": "first", "level": "info", "timestamp": "2026-04-18T00:00:00Z"})
    buf.append({"event": "second", "level": "warning", "timestamp": "2026-04-18T00:01:00Z"})
    buf.append({"event": "third", "level": "error", "timestamp": "2026-04-18T00:02:00Z"})

    resp = await api_client.get("/api/logs?limit=10")
    body = resp.json()
    assert [e["message"] for e in body["events"]] == ["third", "second", "first"]


@pytest.mark.asyncio
async def test_logs_level_filter(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    buf = api_app.state.api_container.log_buffer
    buf.append({"event": "d", "level": "debug"})
    buf.append({"event": "i", "level": "info"})
    buf.append({"event": "w", "level": "warning"})
    buf.append({"event": "e", "level": "error"})

    resp = await api_client.get("/api/logs?level=WARNING")
    body = resp.json()
    # WARNING + above; newest-first.
    assert [e["message"] for e in body["events"]] == ["e", "w"]


@pytest.mark.asyncio
async def test_logs_context_excludes_core_fields(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    buf = api_app.state.api_container.log_buffer
    buf.append(
        {
            "event": "cycle.start",
            "level": "info",
            "timestamp": "2026-04-18T00:00:00Z",
            "symbol": "BTC_USDT",
            "iteration": 7,
        }
    )
    resp = await api_client.get("/api/logs")
    body = resp.json()
    assert body["events"][0]["context"] == {"symbol": "BTC_USDT", "iteration": 7}
