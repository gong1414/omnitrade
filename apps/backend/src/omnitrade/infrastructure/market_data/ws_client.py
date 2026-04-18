"""WSClient — Phase 8.6 WebSocket contract layer.

This module defines the narrow protocol surface that the trading loop and
``MultiTimeframeFetcher`` consume. Real WebSocket implementations live in
sibling modules (``okx_ws.py`` / ``gate_ws.py``). Keeping a thin Protocol
here means the application layer does not depend on exchange-specific
subscribe/authenticate details (Planner v3 S-4: no heavy shared base
class).

WS determinism contract (reference — enforced in
``application/trading_loop.observe_market`` + ``application/monitors/
trading_loop_monitor.TradingLoopMonitor``):

1. A ``WSClient`` = persistent background connection; ``start()`` spawns
   the asyncio reader task, ``stop()`` cleans up.
2. The client buffers one ``TickerUpdate`` per symbol
   (``buffer_snapshot()`` returns a shallow copy).
3. ``observe_market`` takes that snapshot on entry and attaches
   ``ws_buffer_hash = sha256(canonical_json(snapshot))`` to the returned
   ``MarketSnapshot`` (transient — NOT persisted, G-6).
4. ``run_cycle`` downstream reads only the frozen snapshot; it never
   reads the live WS buffer.
5. When ``cassette_mode=True`` or ``USE_WS_MARKET_DATA=false``,
   ``observe_market`` ignores any provided ``ws_client`` and walks the
   REST path unchanged. The monitor's startup assertion refuses to
   run with both flags simultaneously (CRITICAL-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from omnitrade.domain.value_objects import Symbol


@dataclass(frozen=True)
class TickerUpdate:
    """One exchange-pushed ticker update buffered by a ``WSClient``.

    Mirrors the minimum field set that ``MultiTimeframeFetcher`` and
    ``observe_market`` consume. Immutable so a ``buffer_snapshot`` shallow
    copy can be hashed without further defensive copies downstream.
    """

    symbol: str
    price: float
    timestamp_ms: int
    volume_24h: float | None = None


@runtime_checkable
class WSClient(Protocol):
    """Thin async WebSocket ticker-stream contract.

    Implementations must be safe to call ``start()`` exactly once before
    any reader call, and ``stop()`` exactly once at shutdown. Reader
    methods are safe to call from the trading loop between start/stop;
    they MUST return quickly (buffer read only — no network I/O).
    """

    async def start(self) -> None:
        """Spawn the background connection/reader task."""
        ...

    async def stop(self) -> None:
        """Signal shutdown and cancel the background task."""
        ...

    def latest_ticker(self, symbol: Symbol) -> TickerUpdate | None:
        """Return the most recently buffered update for ``symbol`` (or ``None``)."""
        ...

    def buffer_snapshot(self) -> dict[str, TickerUpdate]:
        """Return a shallow copy of the full {symbol: TickerUpdate} buffer.

        The caller may freely iterate / hash this dict; the underlying
        ``TickerUpdate`` instances are frozen so no further copy is
        required. Implementations MUST return a fresh ``dict`` (not the
        live buffer) to preserve the determinism contract.
        """
        ...


__all__ = ["TickerUpdate", "WSClient"]
