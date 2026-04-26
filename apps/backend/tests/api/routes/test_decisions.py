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


@pytest.mark.asyncio
async def test_decisions_serialize_justification_and_run_id(
    api_app, api_client
) -> None:  # type: ignore[no-untyped-def]
    """Regression for alembic 0005/0006 — justification + run_id reach the UI."""
    svc = api_app.state.api_container.decision_service
    long_cot = "Full chain-of-thought. " * 60
    await svc.record(
        iteration=99,
        decision_text="open",
        market_analysis="{}",
        actions_taken="[]",
        account_value=Decimal("1000"),
        positions_count=0,
        justification=long_cot,
    )

    resp = await api_client.get("/api/v1/decisions?limit=1&offset=0")
    assert resp.status_code == 200
    row = resp.json()["decisions"][0]
    assert row["justification"] == long_cot
    # run_id is a real DB column — empty string here because the
    # test harness issues no X-Correlation-ID header, but the key must exist.
    assert "run_id" in row
    assert isinstance(row["run_id"], str)
