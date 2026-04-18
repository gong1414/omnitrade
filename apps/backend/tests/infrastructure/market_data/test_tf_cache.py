"""Unit tests for ``InMemoryTTLCache`` (Phase 8.1)."""

from __future__ import annotations

import asyncio

import pytest

from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache


class _FakeClock:
    """Monotonic clock stub that only moves when ``advance`` is called."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_get_before_set_returns_none() -> None:
    cache: InMemoryTTLCache[int] = InMemoryTTLCache()
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_set_then_get_returns_value() -> None:
    clock = _FakeClock()
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(monotonic_clock=clock)
    await cache.set("k", "v", ttl_seconds=30.0)
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_ttl_expiry_returns_none_and_purges() -> None:
    clock = _FakeClock()
    cache: InMemoryTTLCache[str] = InMemoryTTLCache(monotonic_clock=clock)
    await cache.set("k", "v", ttl_seconds=30.0)
    assert await cache.size() == 1

    clock.advance(29.999)
    assert await cache.get("k") == "v"

    clock.advance(0.002)  # now 30.001 — past TTL
    assert await cache.get("k") is None
    # Expired entry purged by access.
    assert await cache.size() == 0


@pytest.mark.asyncio
async def test_overwrite_refreshes_ttl() -> None:
    clock = _FakeClock()
    cache: InMemoryTTLCache[int] = InMemoryTTLCache(monotonic_clock=clock)
    await cache.set("k", 1, ttl_seconds=10.0)
    clock.advance(9.0)
    await cache.set("k", 2, ttl_seconds=10.0)
    clock.advance(5.0)  # total 14.0 — old TTL would have expired
    assert await cache.get("k") == 2


@pytest.mark.asyncio
async def test_concurrent_set_and_get_no_races() -> None:
    cache: InMemoryTTLCache[int] = InMemoryTTLCache()

    async def writer(i: int) -> None:
        await cache.set(f"k{i}", i, ttl_seconds=60.0)

    async def reader(i: int) -> int | None:
        return await cache.get(f"k{i}")

    await asyncio.gather(*(writer(i) for i in range(50)))
    results = await asyncio.gather(*(reader(i) for i in range(50)))
    assert results == list(range(50))
    assert await cache.size() == 50
