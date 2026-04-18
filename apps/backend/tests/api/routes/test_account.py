"""GET /api/v1/account — returns snapshot dict with peak + drawdown."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_account_returns_live_balance_when_history_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    """No snapshot rows yet → derive from live FakeExchange balance."""
    resp = await api_client.get("/api/v1/account")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_value"] == "1234.5"
    # peak and drawdown always present.
    assert "peak" in body and "drawdown_percent" in body
    # Correlation header is round-tripped by TraceContextMiddleware.
    assert resp.headers.get("X-Correlation-ID")
