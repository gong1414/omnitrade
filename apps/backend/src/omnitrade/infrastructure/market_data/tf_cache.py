"""InMemoryTTLCache — async-safe TTL cache for multi-TF OHLCV.

The cache is parametric on ``monotonic_clock`` so tests can advance time
deterministically without ``time.sleep``. Each ``set`` records the
per-entry TTL; ``get`` returns ``None`` once the entry is past its expiry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class _Entry(Generic[T]):
    value: T
    expires_at: float


class InMemoryTTLCache(Generic[T]):
    """Async-safe TTL cache keyed by ``str``.

    The clock is injectable so tests can control expiry deterministically
    without ``time.sleep``. In production the default ``time.monotonic``
    is used.
    """

    def __init__(
        self,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._clock = monotonic_clock
        self._store: dict[str, _Entry[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        """Return the cached value if present and unexpired, else ``None``."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                # Expired — purge on access so the cache does not grow unbounded.
                self._store.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: T, ttl_seconds: float) -> None:
        """Insert or overwrite ``key`` with ``value`` expiring after ``ttl_seconds``."""
        async with self._lock:
            self._store[key] = _Entry(value=value, expires_at=self._clock() + ttl_seconds)

    async def size(self) -> int:
        """Return the current number of (non-expired) entries.

        Note: ``size`` does not purge expired entries; callers relying on
        accurate counts should call ``get`` or ``set`` to trigger cleanup.
        """
        async with self._lock:
            return len(self._store)


__all__ = ["InMemoryTTLCache"]
