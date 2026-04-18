"""OKX / Gate WebSocket client lifecycle tests (Phase 8.6).

Exercises start/stop semantics and ``buffer_snapshot`` deep-copy
contract without hitting a real network. The underlying reader task is
driven via the public ``_handle_frame`` method so we can feed canned
frames synchronously.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.gate_ws import GateWebSocketClient
from omnitrade.infrastructure.market_data.okx_ws import OKXWebSocketClient
from omnitrade.infrastructure.market_data.ws_client import TickerUpdate


@pytest.mark.asyncio
async def test_okx_start_stop_without_connect() -> None:
    """start() spawns a task; stop() cancels it cleanly when URL is unreachable."""
    client = OKXWebSocketClient(
        symbols=[Symbol(value="BTC_USDT")],
        url="ws://127.0.0.1:1",  # unreachable; reader stays in reconnect loop
        max_consecutive_failures=1,
        degrade_min_seconds=0.05,
        backoff_base=0.01,
        backoff_max=0.02,
        open_timeout=0.2,
    )
    await client.start()
    assert client._task is not None
    # Give the reader a moment to attempt+fail one connect.
    await asyncio.sleep(0.1)
    await client.stop()
    assert client._task is None


def test_okx_handle_frame_updates_buffer() -> None:
    client = OKXWebSocketClient(symbols=[Symbol(value="BTC_USDT")])
    frame = json.dumps(
        {
            "arg": {"channel": "tickers", "instId": "BTC-USDT-SWAP"},
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "last": "42000.5",
                    "ts": "1713443200000",
                    "vol24h": "100",
                }
            ],
        }
    )
    client._handle_frame(frame)

    tick = client.latest_ticker(Symbol(value="BTC_USDT"))
    assert tick is not None
    assert tick.symbol == "BTC_USDT"
    assert tick.price == 42000.5
    assert tick.timestamp_ms == 1713443200000
    assert tick.volume_24h == 100.0


def test_okx_buffer_snapshot_is_copy() -> None:
    client = OKXWebSocketClient(symbols=[Symbol(value="BTC_USDT")])
    client._buffer["BTC_USDT"] = TickerUpdate(
        symbol="BTC_USDT", price=100.0, timestamp_ms=1, volume_24h=1.0
    )
    snap = client.buffer_snapshot()
    assert snap == {"BTC_USDT": client._buffer["BTC_USDT"]}
    # Mutating the snapshot must NOT leak into the live buffer.
    snap.pop("BTC_USDT")
    assert "BTC_USDT" in client._buffer


def test_okx_handle_frame_ignores_malformed_payload() -> None:
    client = OKXWebSocketClient(symbols=[Symbol(value="BTC_USDT")])
    client._handle_frame("not json")
    client._handle_frame(json.dumps({"event": "subscribe"}))
    client._handle_frame(json.dumps({"data": "not a list"}))
    assert client.buffer_snapshot() == {}


def test_gate_handle_frame_updates_buffer() -> None:
    client = GateWebSocketClient(symbols=[Symbol(value="BTC_USDT")])
    frame = json.dumps(
        {
            "channel": "futures.tickers",
            "event": "update",
            "result": [{"contract": "BTC_USDT", "last": "42000.5", "volume_24h": "200"}],
        }
    )
    client._handle_frame(frame)
    tick = client.latest_ticker(Symbol(value="BTC_USDT"))
    assert tick is not None
    assert tick.price == 42000.5
    assert tick.volume_24h == 200.0


@pytest.mark.asyncio
async def test_gate_start_stop_without_connect() -> None:
    client = GateWebSocketClient(
        symbols=[Symbol(value="BTC_USDT")],
        url="ws://127.0.0.1:1",
        max_consecutive_failures=1,
        degrade_min_seconds=0.05,
        backoff_base=0.01,
        backoff_max=0.02,
        open_timeout=0.2,
    )
    await client.start()
    assert client._task is not None
    await asyncio.sleep(0.1)
    await client.stop()
    assert client._task is None
