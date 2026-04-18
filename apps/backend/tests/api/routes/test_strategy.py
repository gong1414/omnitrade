"""GET /api/strategy — Settings-derived strategy snapshot."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_strategy_snapshot_matches_settings(api_settings, api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/strategy")
    assert resp.status_code == 200
    body = resp.json()

    assert body["name"] == api_settings.trading_strategy
    assert body["interval_minutes"] == api_settings.trading_interval_minutes
    assert body["max_leverage"] == api_settings.max_leverage
    assert body["max_positions"] == api_settings.max_positions
    assert body["max_holding_hours"] == api_settings.max_holding_hours
    # Phase 8.5a placeholder.
    assert body["multi_agent_enabled"] is False
