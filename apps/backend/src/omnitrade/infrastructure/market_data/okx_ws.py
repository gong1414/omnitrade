"""OKXWebSocketClient — OKX v5 public ticker stream (Phase 8.6).

Hand-rolled against ``websockets>=12`` per ADR-F (F2). Preserves
subscribe-once / reconnect-with-backoff / degrade-to-REST semantics
behind the narrow Python ``WSClient`` Protocol defined in
``ws_client.py``.

Observability (plan §6.6): reconnect attempts emit
``ws.reconnect_total{exchange="okx"}``, and each entry into
degraded-REST mode emits ``ws.degrade_total{exchange="okx"}``.

Degrade rule: 3 consecutive failed connect attempts → the client flips
to ``_degraded=True`` for at least ``DEGRADE_MIN_SECONDS``. While
degraded, ``latest_ticker`` / ``buffer_snapshot`` continue to return the
last known buffer (possibly empty); the trading loop's
``observe_market`` code path reads the ``WSClient`` contract as advisory
— the caller is expected to fall back to REST when the buffer is empty
or stale.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.ws_client import TickerUpdate
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

# OKX v5 public WS URL (non-private channels only).
_OKX_WS_URL: str = "wss://ws.okx.com:8443/ws/v5/public"

# Reconnect / degrade thresholds (contract §6).
_MAX_CONSECUTIVE_FAILURES: int = 3
DEGRADE_MIN_SECONDS: float = 30.0
_PING_INTERVAL_SECONDS: float = 20.0
_PING_TIMEOUT_SECONDS: float = 10.0

# Exponential backoff bounds for the reconnect loop.
_BACKOFF_BASE: float = 0.5
_BACKOFF_MAX: float = 30.0


class OKXWebSocketClient:
    """OKX v5 public ticker stream exposed via the ``WSClient`` Protocol.

    Args:
        symbols: Initial symbol universe (e.g. ``[Symbol(value="BTC_USDT")]``).
            Symbol string is translated to OKX ``instId`` (``BTC-USDT``).
        url: Override the public WS endpoint (tests).
        max_consecutive_failures: Degrade threshold; default 3.
        degrade_min_seconds: Min dwell time in degraded mode; default 30s.
    """

    def __init__(
        self,
        *,
        symbols: list[Symbol] | None = None,
        url: str = _OKX_WS_URL,
        max_consecutive_failures: int = _MAX_CONSECUTIVE_FAILURES,
        degrade_min_seconds: float = DEGRADE_MIN_SECONDS,
        backoff_base: float = _BACKOFF_BASE,
        backoff_max: float = _BACKOFF_MAX,
        open_timeout: float = 10.0,
    ) -> None:
        self._symbols: list[Symbol] = list(symbols or [])
        self._url = url
        self._max_consecutive_failures = max_consecutive_failures
        self._degrade_min_seconds = degrade_min_seconds
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._open_timeout = open_timeout

        self._buffer: dict[str, TickerUpdate] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._degraded: bool = False
        self._degraded_until: float = 0.0
        self._consecutive_failures: int = 0

        # Exposed for tests / observability.
        self.reconnect_total: int = 0
        self.degrade_total: int = 0

    # ── public contract ──────────────────────────────────────────────── #

    async def start(self) -> None:
        """Spawn the background reader task (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="okx_ws_reader")

    async def stop(self) -> None:
        """Signal shutdown and await the background task."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: S110 — teardown only
                pass
            self._task = None

    def latest_ticker(self, symbol: Symbol) -> TickerUpdate | None:
        return self._buffer.get(symbol.value)

    def buffer_snapshot(self) -> dict[str, TickerUpdate]:
        # Shallow copy; TickerUpdate is frozen.
        return dict(self._buffer)

    # ── internals ────────────────────────────────────────────────────── #

    @property
    def degraded(self) -> bool:
        """True if the client is currently in degraded (REST-fallback) mode."""
        if not self._degraded:
            return False
        if time.monotonic() >= self._degraded_until:
            self._degraded = False
            return False
        return True

    def _enter_degraded(self) -> None:
        self._degraded = True
        self._degraded_until = time.monotonic() + self._degrade_min_seconds
        self.degrade_total += 1
        with_context(logger).warning(
            "ws.degrade_total",
            exchange="okx",
            count=self.degrade_total,
            degrade_seconds=self._degrade_min_seconds,
        )

    def _inst_id(self, symbol: Symbol) -> str:
        """Map ``BTC_USDT`` → OKX ``BTC-USDT-SWAP`` for perpetual futures."""
        base_quote = symbol.value.replace("_", "-")
        # OKX SWAP product suffix for futures ticker channel.
        if base_quote.endswith("-SWAP"):
            return base_quote
        return f"{base_quote}-SWAP"

    def _subscribe_payload(self) -> str:
        args = [{"channel": "tickers", "instId": self._inst_id(s)} for s in self._symbols]
        return json.dumps({"op": "subscribe", "args": args})

    async def _run(self) -> None:
        """Reader loop — (re)connect, subscribe, consume messages."""
        attempt = 0
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=_PING_INTERVAL_SECONDS,
                    ping_timeout=_PING_TIMEOUT_SECONDS,
                    close_timeout=5,
                    open_timeout=self._open_timeout,
                ) as ws:
                    self._consecutive_failures = 0
                    attempt = 0
                    if self._symbols:
                        await ws.send(self._subscribe_payload())
                    with_context(logger).info(
                        "ws.connected",
                        exchange="okx",
                        n_symbols=len(self._symbols),
                    )
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, WebSocketException, OSError) as exc:
                self._consecutive_failures += 1
                self.reconnect_total += 1
                with_context(logger).warning(
                    "ws.reconnect_total",
                    exchange="okx",
                    consecutive_failures=self._consecutive_failures,
                    count=self.reconnect_total,
                    error=str(exc),
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._enter_degraded()
            except Exception as exc:  # defensive: any other unexpected error
                self._consecutive_failures += 1
                self.reconnect_total += 1
                with_context(logger).error(
                    "ws.unexpected_error",
                    exchange="okx",
                    error=str(exc),
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._enter_degraded()

            if self._stop_event.is_set():
                break

            # Exponential backoff with jitter; bounded by ``backoff_max``.
            attempt += 1
            sleep_s = min(self._backoff_base * (2 ** min(attempt, 6)), self._backoff_max)
            sleep_s *= 0.5 + random.random() * 0.5  # noqa: S311 (jitter only)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_s)
            except TimeoutError:
                continue

    async def _consume(self, ws: Any) -> None:
        """Read frames until the socket closes or ``_stop_event`` fires."""
        while not self._stop_event.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_PING_INTERVAL_SECONDS * 2)
            except TimeoutError:
                # No frames in 2x ping interval — force reconnect.
                raise ConnectionClosed(None, None) from None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            self._handle_frame(raw)

    def _handle_frame(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return
        for entry in data:
            if not isinstance(entry, dict):
                continue
            inst_id = entry.get("instId")
            last = entry.get("last")
            ts_raw = entry.get("ts")
            vol_raw = entry.get("vol24h")
            if not isinstance(inst_id, str) or last is None:
                continue
            try:
                price = float(last)
                ts_ms = int(ts_raw) if ts_raw is not None else int(time.time() * 1000)
                vol_24h = float(vol_raw) if vol_raw is not None else None
            except (TypeError, ValueError):
                continue
            symbol_str = inst_id.replace("-SWAP", "").replace("-", "_")
            self._buffer[symbol_str] = TickerUpdate(
                symbol=symbol_str,
                price=price,
                timestamp_ms=ts_ms,
                volume_24h=vol_24h,
            )


__all__ = ["DEGRADE_MIN_SECONDS", "OKXWebSocketClient"]
