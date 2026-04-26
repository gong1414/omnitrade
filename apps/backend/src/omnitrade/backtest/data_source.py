"""HistoricalOHLCV — sqlite-cached Binance public OHLCV feed.

Binance public market data does NOT require authentication, so the
backtest harness can pull historical candles via ``ccxt.async_support.
binance()`` without API keys. Fetches are cached to
``.backtest/ohlcv_cache.db`` keyed on ``(symbol, timeframe,
ts_ms)`` so repeated backtests over the same window become
disk-bound after the first run.

Symbol conventions
------------------
Internal symbols follow Gate convention (``BTC_USDT``). Binance's ccxt
unified form is ``BTC/USDT``. The ``_to_ccxt_symbol`` helper handles
the translation (spot symbols — Binance futures uses ``:USDT`` suffix
but for backtesting spot OHLCV is the right proxy, since we're
simulating leveraged positions against spot-like price action).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:  # avoid importing heavy ccxt at module load time
    pass

logger = structlog.get_logger(__name__)


_TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


def timeframe_to_ms(timeframe: str) -> int:
    """Convert a ccxt timeframe label to milliseconds."""
    try:
        return _TIMEFRAME_MS[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}") from exc


def _to_ccxt_symbol(internal: str) -> str:
    """Translate ``BTC_USDT`` (Gate convention) → ``BTC/USDT`` (Binance ccxt)."""
    if "/" in internal:
        return internal
    if "_" in internal:
        base, quote = internal.split("_", 1)
        return f"{base}/{quote}"
    return internal


class HistoricalOHLCV:
    """Cached historical candles for backtesting.

    The cache key is ``(symbol, timeframe, ts_ms)``. ``load`` returns
    a sorted ``list[list[float]]`` covering ``[start_ts, end_ts]``
    inclusive, fetching any gaps from Binance in 1000-row batches
    (Binance's public limit) and inserting the new rows back into the
    cache.

    Args:
        cache_path: Path to the sqlite DB. Parent dirs are created.
        exchange_factory: Injection seam for tests — returns an object
            with an ``fetch_ohlcv(symbol, timeframe, since, limit)``
            coroutine matching the ccxt async surface, plus a ``close()``
            coroutine for cleanup. Default lazily builds a real
            ``ccxt.async_support.binance`` instance.
    """

    def __init__(
        self,
        cache_path: Path | str,
        *,
        exchange_factory: Any | None = None,
    ) -> None:
        self._path = Path(cache_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ohlcv_cache ("
            "symbol TEXT NOT NULL, "
            "timeframe TEXT NOT NULL, "
            "ts_ms INTEGER NOT NULL, "
            "o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, "
            "c REAL NOT NULL, v REAL NOT NULL, "
            "PRIMARY KEY(symbol, timeframe, ts_ms))"
        )
        self._conn.commit()
        self._exchange_factory = exchange_factory
        self._exchange: Any | None = None

    # ── exchange lazy init ─────────────────────────────────────────── #

    async def _get_exchange(self) -> Any:
        if self._exchange is not None:
            return self._exchange
        if self._exchange_factory is not None:
            self._exchange = await _maybe_await(self._exchange_factory())
        else:
            import ccxt.async_support as ccxt_async

            self._exchange = ccxt_async.gate({"enableRateLimit": True})
        return self._exchange

    async def close(self) -> None:
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception:
                # Best-effort cleanup during shutdown.
                pass
            self._exchange = None
        try:
            self._conn.close()
        except Exception:
            # Best-effort cleanup during shutdown.
            pass

    # ── cache IO ───────────────────────────────────────────────────── #

    def _select_range(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
    ) -> list[list[float]]:
        cur = self._conn.execute(
            "SELECT ts_ms, o, h, l, c, v FROM ohlcv_cache "
            "WHERE symbol = ? AND timeframe = ? AND ts_ms >= ? AND ts_ms <= ? "
            "ORDER BY ts_ms ASC",
            (symbol, timeframe, start_ts, end_ts),
        )
        return [
            [float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
            for r in cur.fetchall()
        ]

    def _insert_rows(self, symbol: str, timeframe: str, rows: list[list[float]]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO ohlcv_cache "
                "(symbol, timeframe, ts_ms, o, h, l, c, v) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        symbol,
                        timeframe,
                        int(r[0]),
                        float(r[1]),
                        float(r[2]),
                        float(r[3]),
                        float(r[4]),
                        float(r[5]),
                    )
                    for r in rows
                ],
            )
            self._conn.commit()

    # ── public API ─────────────────────────────────────────────────── #

    async def load(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
    ) -> list[list[float]]:
        """Return candles in ``[start_ts, end_ts]`` (ms, inclusive).

        Fetches from Binance in 1000-row batches on cache miss and
        persists the rows before returning.
        """
        if end_ts < start_ts:
            raise ValueError(f"end_ts {end_ts} < start_ts {start_ts}")

        step_ms = timeframe_to_ms(timeframe)

        cached = self._select_range(symbol, timeframe, start_ts, end_ts)
        cached_ts = {int(r[0]) for r in cached}

        expected_count = (end_ts - start_ts) // step_ms + 1
        if len(cached_ts) >= expected_count:
            # Already covered — no need to fetch.
            logger.debug(
                "historical_ohlcv.cache_full",
                symbol=symbol,
                timeframe=timeframe,
                rows=len(cached),
            )
            return sorted(cached, key=lambda r: r[0])

        # Find contiguous gaps and fetch them.
        ccxt_symbol = _to_ccxt_symbol(symbol)
        exchange = await self._get_exchange()

        since = start_ts
        fetched_total: list[list[float]] = []
        while since <= end_ts:
            batch_limit = 1000
            logger.info(
                "historical_ohlcv.fetch_batch",
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                limit=batch_limit,
            )
            raw = await exchange.fetch_ohlcv(
                ccxt_symbol, timeframe=timeframe, since=since, limit=batch_limit
            )
            if not raw:
                break
            rows: list[list[float]] = [[float(x) for x in row] for row in raw]
            # Filter to window + only rows not already cached.
            new_rows = [
                r for r in rows if start_ts <= int(r[0]) <= end_ts and int(r[0]) not in cached_ts
            ]
            self._insert_rows(symbol, timeframe, new_rows)
            cached_ts.update(int(r[0]) for r in new_rows)
            fetched_total.extend(new_rows)
            # Advance past the last bar returned; break if exchange
            # didn't advance (prevents infinite loop on stale data).
            last_ts = int(rows[-1][0])
            next_since = last_ts + step_ms
            if next_since <= since:
                break
            since = next_since
            if len(rows) < batch_limit:
                # Exhausted available history.
                break

        # Re-read the whole range to get a sorted, deduped view.
        return self._select_range(symbol, timeframe, start_ts, end_ts)


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` when it's a coroutine, otherwise return as-is."""
    if hasattr(value, "__await__"):
        return await value
    return value


def iso_to_ms(iso: str) -> int:
    """Parse an ISO date/datetime string to Unix milliseconds (UTC)."""
    # Accept both "2026-01-01" and full "2026-01-01T00:00:00".
    if "T" not in iso:
        iso = f"{iso}T00:00:00"
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


__all__ = ["HistoricalOHLCV", "iso_to_ms", "timeframe_to_ms"]
