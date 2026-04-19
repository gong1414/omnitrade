"""BacktestClock — injectable wall-clock replacement for the engine.

The production ``composition._build_base_think_fn`` reads
``datetime.now(tz=UTC)`` only inside ``_render_recent_trades_block``;
the think_fn we build for backtest does NOT use that path. The clock
is nevertheless exposed because the engine's equity-curve timestamps
and the ``MarketSnapshot.timestamp`` it builds must advance bar-by-bar
(not wall-clock), so every downstream caller reads the engine's
``BacktestClock.now()`` rather than the process clock.
"""

from __future__ import annotations

from datetime import UTC, datetime


class BacktestClock:
    """Monotonic manual-advance clock used by ``BacktestEngine``."""

    def __init__(self, start: datetime | None = None) -> None:
        if start is None:
            start = datetime(2026, 1, 1, tzinfo=UTC)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        self._now: datetime = start

    def now(self) -> datetime:
        return self._now

    def set_now(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        self._now = dt


__all__ = ["BacktestClock"]
