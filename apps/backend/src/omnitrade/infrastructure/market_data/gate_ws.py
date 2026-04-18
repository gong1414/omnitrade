"""GateWebSocketClient — Gate.io futures USDT-perp ticker stream (Phase 8.6).

Hand-rolled against ``websockets>=12`` per ADR-F (F2). Mirrors
``okx_ws.py`` in shape; subscribe payload + message schema are
Gate-specific (``futures.tickers`` channel on
``wss://fx-ws.gateio.ws/v4/ws/usdt``). No shared heavyweight base class
(Planner v3 S-4): the two clients only share the ``WSClient`` Protocol.

Observability + degrade semantics match ``okx_ws.py``; counters are
tagged ``exchange="gate"``.
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

# Gate.io futures USDT perpetual public WS URL.
_GATE_WS_URL: str = "wss://fx-ws.gateio.ws/v4/ws/usdt"

_MAX_CONSECUTIVE_FAILURES: int = 3
DEGRADE_MIN_SECONDS: float = 30.0
_PING_INTERVAL_SECONDS: float = 20.0
_PING_TIMEOUT_SECONDS: float = 10.0

_BACKOFF_BASE: float = 0.5
_BACKOFF_MAX: float = 30.0


class GateWebSocketClient:
    """Gate.io futures USDT-perp ticker stream (``WSClient`` Protocol)."""

    def __init__(
        self,
        *,
        symbols: list[Symbol] | None = None,
        url: str = _GATE_WS_URL,
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

        self.reconnect_total: int = 0
        self.degrade_total: int = 0

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="gate_ws_reader")

    async def stop(self) -> None:
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
        return dict(self._buffer)

    @property
    def degraded(self) -> bool:
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
            exchange="gate",
            count=self.degrade_total,
            degrade_seconds=self._degrade_min_seconds,
        )

    def _contract(self, symbol: Symbol) -> str:
        """Map ``BTC_USDT`` → Gate ``BTC_USDT`` contract id (already matches)."""
        return symbol.value

    def _subscribe_payload(self) -> str:
        # Single aggregated subscribe frame; channel ``futures.tickers`` with
        # the full contract list as the payload (Gate v4 docs).
        return json.dumps(
            {
                "time": int(time.time()),
                "channel": "futures.tickers",
                "event": "subscribe",
                "payload": [self._contract(s) for s in self._symbols],
            }
        )

    async def _run(self) -> None:
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
                        exchange="gate",
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
                    exchange="gate",
                    consecutive_failures=self._consecutive_failures,
                    count=self.reconnect_total,
                    error=str(exc),
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._enter_degraded()
            except Exception as exc:
                self._consecutive_failures += 1
                self.reconnect_total += 1
                with_context(logger).error(
                    "ws.unexpected_error",
                    exchange="gate",
                    error=str(exc),
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    self._enter_degraded()

            if self._stop_event.is_set():
                break

            attempt += 1
            sleep_s = min(self._backoff_base * (2 ** min(attempt, 6)), self._backoff_max)
            sleep_s *= 0.5 + random.random() * 0.5  # noqa: S311 (jitter only)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_s)
            except TimeoutError:
                continue

    async def _consume(self, ws: Any) -> None:
        while not self._stop_event.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_PING_INTERVAL_SECONDS * 2)
            except TimeoutError:
                raise ConnectionClosed(None, None) from None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            self._handle_frame(raw)

    def _handle_frame(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        # Gate wraps updates under ``result``; event-type "update" carries
        # data, "subscribe"/"unsubscribe" do not.
        event = payload.get("event")
        if event and event not in {"update", "all"}:
            return
        result = payload.get("result")
        entries: list[Any]
        if isinstance(result, list):
            entries = result
        elif isinstance(result, dict):
            entries = [result]
        else:
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            contract = entry.get("contract")
            last = entry.get("last")
            vol_raw = entry.get("volume_24h")
            if not isinstance(contract, str) or last is None:
                continue
            try:
                price = float(last)
                vol_24h = float(vol_raw) if vol_raw is not None else None
            except (TypeError, ValueError):
                continue
            ts_ms = int(time.time() * 1000)
            symbol_str = contract
            self._buffer[symbol_str] = TickerUpdate(
                symbol=symbol_str,
                price=price,
                timestamp_ms=ts_ms,
                volume_24h=vol_24h,
            )


__all__ = ["DEGRADE_MIN_SECONDS", "GateWebSocketClient"]
