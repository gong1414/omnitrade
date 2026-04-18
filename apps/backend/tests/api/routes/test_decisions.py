"""GET /api/v1/decisions — pagination."""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_decisions_paginate(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    svc = api_app.state.api_container.decision_service
    for i in range(5):
        await svc.record(
            iteration=i,
            decision_text=f"action-{i}",
            market_analysis="{}",
            actions_taken="[]",
            account_value=Decimal("1000"),
            positions_count=0,
        )

    resp = await api_client.get("/api/v1/decisions?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    # Newest first → action-4 then action-3.
    assert body["decisions"][0]["decision"] == "action-4"
    assert body["decisions"][1]["decision"] == "action-3"

    resp2 = await api_client.get("/api/v1/decisions?limit=2&offset=2")
    body2 = resp2.json()
    assert body2["decisions"][0]["decision"] == "action-2"
    assert body2["decisions"][1]["decision"] == "action-1"


@pytest.mark.asyncio
async def test_decisions_query_bounds(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/decisions?limit=0")
    assert resp.status_code == 422
    resp = await api_client.get("/api/v1/decisions?limit=1000")
    assert resp.status_code == 422
