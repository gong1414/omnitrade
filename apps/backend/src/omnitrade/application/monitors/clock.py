"""Monotonic clock protocol for monitor determinism.

Every monitor receives a ``ClockProtocol`` so unit tests can drive the
tick path without ``datetime.now()`` drift.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClockProtocol(Protocol):
    """Minimal wall-clock abstraction."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default ``ClockProtocol`` backed by ``datetime.now(tz=UTC)``."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


Clock = ClockProtocol  # alias for readability at call-sites

__all__ = ["Clock", "ClockProtocol", "SystemClock"]
