"""WS reconnect / degrade fuzz (Phase 8.6).

The reader loop refuses to connect against an unreachable URL. After
``max_consecutive_failures`` connect attempts the client MUST flip to
degraded mode for at least ``degrade_min_seconds`` and emit matching
``ws.reconnect_total`` + ``ws.degrade_total`` counters.
"""

from __future__ import annotations

import asyncio

import pytest

from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.okx_ws import OKXWebSocketClient


@pytest.mark.asyncio
async def test_three_failures_enter_degraded_mode() -> None:
    client = OKXWebSocketClient(
        symbols=[Symbol(value="BTC_USDT")],
        url="ws://127.0.0.1:1",  # guaranteed-unreachable
        max_consecutive_failures=3,
        degrade_min_seconds=0.5,
        # Tight backoff + open_timeout so the test finishes in <2s even
        # on slow CI; each connect attempt errors almost immediately.
        backoff_base=0.005,
        backoff_max=0.02,
        open_timeout=0.2,
    )
    await client.start()

    for _ in range(200):
        if client.degrade_total >= 1 and client.reconnect_total >= 3:
            break
        await asyncio.sleep(0.05)
    await client.stop()

    assert client.reconnect_total >= 3, (
        f"expected >=3 reconnect attempts, got {client.reconnect_total}"
    )
    assert client.degrade_total >= 1
    # At least one failure flipped the degraded flag — even if the
    # dwell window has expired by the time we assert, the counter
    # increment proves the state transition happened.


@pytest.mark.asyncio
async def test_degrade_flag_auto_clears_after_min_seconds() -> None:
    client = OKXWebSocketClient(
        symbols=[Symbol(value="BTC_USDT")],
        url="ws://127.0.0.1:1",
        max_consecutive_failures=3,
        degrade_min_seconds=0.05,
    )
    # Force the degraded flag directly to avoid depending on timing of
    # the reader task.
    client._enter_degraded()
    assert client.degraded is True
    await asyncio.sleep(0.1)
    assert client.degraded is False
