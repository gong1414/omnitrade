"""GET /api/v1/rebate — summary endpoint round-trip."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_rebate_summary_shape(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/v1/rebate")
    assert resp.status_code == 200
    body = resp.json()
    required = {
        "window_start",
        "window_end",
        "fee_rebate_percent",
        "close_trades_count",
        "total_fees_usdt",
        "rebate_amount_usdt",
    }
    assert required.issubset(body.keys())
    # Empty history → zero counts.
    assert body["close_trades_count"] == 0
    assert body["total_fees_usdt"] == "0"
