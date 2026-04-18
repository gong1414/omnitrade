"""observe_market(cassette_mode=True) forces REST even when ws_client is set.

Phase 8.6 MAJOR-5 contract item 4: cassette mode must ignore any
``WSClient`` argument so byte-replay stays deterministic. We spy on the
``WSClient`` to prove ``buffer_snapshot`` is never consulted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.trading_loop import observe_market
from omnitrade.domain.entities import MarketSnapshot
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.ws_client import TickerUpdate


class _SpyWSClient:
    def __init__(self) -> None:
        self.snapshot_calls: int = 0
        self.latest_calls: int = 0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def latest_ticker(self, _symbol: Symbol) -> TickerUpdate | None:
        self.latest_calls += 1
        return None

    def buffer_snapshot(self) -> dict[str, TickerUpdate]:
        self.snapshot_calls += 1
        return {
            "BTC_USDT": TickerUpdate(
                symbol="BTC_USDT", price=42000.0, timestamp_ms=1, volume_24h=1.0
            )
        }


def _snap() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("42000")},
        positions=[],
    )


@pytest.mark.asyncio
async def test_cassette_mode_ignores_ws_client() -> None:
    spy = _SpyWSClient()

    async def observe() -> MarketSnapshot:
        return _snap()

    out = await observe_market(observe, spy, cassette_mode=True)  # type: ignore[arg-type]
    assert out.ws_buffer_hash is None, "cassette mode must never set ws_buffer_hash"
    assert spy.snapshot_calls == 0
    assert spy.latest_calls == 0


@pytest.mark.asyncio
async def test_ws_mode_attaches_hash() -> None:
    spy = _SpyWSClient()

    async def observe() -> MarketSnapshot:
        return _snap()

    out = await observe_market(observe, spy, cassette_mode=False)  # type: ignore[arg-type]
    assert out.ws_buffer_hash is not None
    assert spy.snapshot_calls == 1


@pytest.mark.asyncio
async def test_no_ws_client_is_noop() -> None:
    async def observe() -> MarketSnapshot:
        return _snap()

    out = await observe_market(observe)
    assert out.ws_buffer_hash is None
