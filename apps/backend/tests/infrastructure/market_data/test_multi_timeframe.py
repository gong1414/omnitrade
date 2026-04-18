"""Unit tests for ``MultiTimeframeFetcher`` (Phase 8.1)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.multi_timeframe import (
    MultiTimeframeFetcher,
    ttl_for_timeframe,
)
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache


class _StubExchange:
    """Minimal ExchangeClient stub implementing only ``fetch_ohlcv``.

    Records every call so tests can assert call counts + ordering.
    """

    def __init__(
        self,
        *,
        delay: float = 0.0,
        builder: Callable[[Symbol, str, int], list[list[float]]] | None = None,
    ) -> None:
        self._delay = delay
        self._builder = builder or (
            lambda sym, tf, limit: [[0.0, 1.0, 1.0, 1.0, 1.0, 10.0] for _ in range(limit)]
        )
        self.calls: list[tuple[str, str, int]] = []
        self._lock = asyncio.Lock()
        self.max_in_flight = 0
        self._in_flight = 0

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int = 100,
    ) -> list[list[float]]:
        async with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            self.calls.append((symbol.value, timeframe, limit))
            return self._builder(symbol, timeframe, limit)
        finally:
            async with self._lock:
                self._in_flight -= 1


@pytest.mark.parametrize(
    ("tf", "expected"),
    [
        ("1m", 30.0),
        ("3m", 30.0),
        ("5m", 30.0),
        ("15m", 60.0),
        ("30m", 60.0),
        ("1h", 60.0),
        ("4h", 300.0),
        ("1d", 300.0),
        ("unknown-xx", 60.0),  # safe mid-bucket fallback
    ],
)
def test_ttl_per_timeframe(tf: str, expected: float) -> None:
    assert ttl_for_timeframe(tf) == expected


@pytest.mark.asyncio
async def test_first_fetch_hits_exchange_second_hits_cache() -> None:
    exchange = _StubExchange()
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=cache,
    )
    sym = Symbol(value="BTC_USDT")

    first = await fetcher.fetch(sym, ["5m"])
    assert list(first.keys()) == ["5m"]
    assert len(exchange.calls) == 1

    second = await fetcher.fetch(sym, ["5m"])
    assert second == first
    # Cached, no new exchange calls.
    assert len(exchange.calls) == 1


@pytest.mark.asyncio
async def test_fetch_preserves_requested_tf_order() -> None:
    exchange = _StubExchange()
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(exchange=exchange, cache=cache)  # type: ignore[arg-type]
    sym = Symbol(value="BTC_USDT")

    tfs = ["15m", "1h", "4h", "1d"]
    result = await fetcher.fetch(sym, tfs)
    assert list(result.keys()) == tfs


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency() -> None:
    exchange = _StubExchange(delay=0.02)
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=cache,
        # Tiny rps → permits = max(2 // 2, 8) = 8. Sanity floor.
        rate_limit_rps=2,
    )
    assert fetcher.semaphore_permits == 8

    # 20 unique (symbol, tf) pairs to force concurrent fan-out.
    symbols = [Symbol(value=f"SYM{i}_USDT") for i in range(20)]
    await asyncio.gather(
        *(fetcher.fetch(sym, ["5m"]) for sym in symbols)
    )
    assert exchange.max_in_flight <= 8


@pytest.mark.asyncio
async def test_semaphore_respects_configured_rps() -> None:
    exchange = _StubExchange(delay=0.02)
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=cache,
        rate_limit_rps=64,
    )
    # rps 64 → permits = max(32, 8) = 32.
    assert fetcher.semaphore_permits == 32


@pytest.mark.asyncio
async def test_limit_kwarg_threads_to_exchange() -> None:
    exchange = _StubExchange()
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=cache,
        limit=42,
    )
    sym = Symbol(value="ETH_USDT")
    await fetcher.fetch(sym, ["1h"])
    assert exchange.calls == [("ETH_USDT", "1h", 42)]
