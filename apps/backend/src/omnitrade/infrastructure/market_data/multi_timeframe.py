"""MultiTimeframeFetcher — per-cycle multi-TF OHLCV fan-out.

Fetches multiple timeframes concurrently (bounded by an
``asyncio.Semaphore``) and caches each (symbol, tf) result with a
TF-appropriate TTL. Each fetch emits a structlog event
``market_data.multi_tf.fetched`` with ``{symbol, tf, cache_hit}``.

This is a Phase-8.1 component; the Phase-8.5a multi-agent orchestrator
composes the fetcher into the ``ThinkFn`` chain via
``application.multi_agent.composition.build_think_fn``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache
from omnitrade.infrastructure.market_data.ws_client import WSClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

# Per-TF TTL seconds (consensus plan §5 Phase 8.1).
_TTL_FAST: frozenset[str] = frozenset({"1m", "3m", "5m"})
_TTL_MID: frozenset[str] = frozenset({"15m", "30m", "1h"})
_TTL_SLOW: frozenset[str] = frozenset({"4h", "1d"})

# Default per-TF OHLCV candle limit.
_DEFAULT_LIMIT: int = 100


def ttl_for_timeframe(timeframe: str) -> float:
    """Return the TTL (seconds) for a given timeframe string.

    * 1m / 3m / 5m   → 30s
    * 15m / 30m / 1h → 60s
    * 4h / 1d        → 300s
    * unknown        → 60s (safe mid-bucket default)
    """
    if timeframe in _TTL_FAST:
        return 30.0
    if timeframe in _TTL_SLOW:
        return 300.0
    if timeframe in _TTL_MID:
        return 60.0
    return 60.0


class MultiTimeframeFetcher:
    """Fetch multiple (symbol, timeframe) OHLCV slices with rate/TTL control.

    Args:
        exchange: Protocol-typed ``ExchangeClient`` (ccxt adapter in prod).
        cache: TTL cache keyed ``f"{symbol}|{tf}"``. One cache instance is
            shared across TFs; per-entry TTL varies.
        rate_limit_rps: Upstream-parity RPS budget. Semaphore permits =
            ``max(rate_limit_rps // 2, 8)``.
        limit: Per-TF candle count (default 100).
    """

    def __init__(
        self,
        *,
        exchange: ExchangeClient,
        cache: InMemoryTTLCache[list[list[float]]],
        rate_limit_rps: int = 16,
        limit: int = _DEFAULT_LIMIT,
        ws_client: WSClient | None = None,
    ) -> None:
        self._exchange = exchange
        self._cache = cache
        permits = max(rate_limit_rps // 2, 8)
        self._semaphore = asyncio.Semaphore(permits)
        self._limit = limit
        self._permits = permits
        # Phase 8.6: optional WS ticker source. When present AND the
        # requested timeframe is ``1m``/``3m``/``5m`` AND the client is
        # not degraded, ``_fetch_one`` returns a single-candle synthetic
        # OHLCV row built from the most recent ``TickerUpdate`` instead
        # of going to REST. All other TFs still go through REST.
        self._ws_client = ws_client

    @property
    def semaphore_permits(self) -> int:
        """Configured semaphore permit count (exposed for observability/tests)."""
        return self._permits

    async def fetch(
        self,
        symbol: Symbol,
        timeframes: list[str],
    ) -> dict[str, list[Any]]:
        """Fetch OHLCV for every ``tf`` in ``timeframes`` for a single symbol.

        Returns a dict ``{tf: [[ts, o, h, l, c, v], ...]}``. Order of keys
        matches the input ``timeframes`` order for determinism.
        """
        results: dict[str, list[Any]] = {}
        tasks: list[asyncio.Task[tuple[str, list[Any]]]] = [
            asyncio.create_task(self._fetch_one(symbol, tf)) for tf in timeframes
        ]
        for coro in asyncio.as_completed(tasks):
            tf_name, ohlcv = await coro
            results[tf_name] = ohlcv
        # Preserve requested-order key iteration.
        return {tf: results[tf] for tf in timeframes if tf in results}

    async def _fetch_one(
        self,
        symbol: Symbol,
        timeframe: str,
    ) -> tuple[str, list[Any]]:
        key = f"{symbol.value}|{timeframe}"
        cached = await self._cache.get(key)
        if cached is not None:
            with_context(logger).info(
                "market_data.multi_tf.fetched",
                symbol=symbol.value,
                tf=timeframe,
                cache_hit=True,
            )
            return timeframe, cached

        # Phase 8.6: prefer WS-derived pseudo-OHLCV for fast TFs when the
        # WS client is wired AND not degraded. For degraded / non-fast
        # TFs we fall straight through to REST.
        if (
            self._ws_client is not None
            and timeframe in _TTL_FAST
            and not getattr(self._ws_client, "degraded", False)
        ):
            tick = self._ws_client.latest_ticker(symbol)
            if tick is not None:
                # Single-candle pseudo-OHLCV: [ts_ms, o, h, l, c, v].
                vol = float(tick.volume_24h) if tick.volume_24h is not None else 0.0
                pseudo: list[list[float]] = [
                    [
                        float(tick.timestamp_ms),
                        tick.price,
                        tick.price,
                        tick.price,
                        tick.price,
                        vol,
                    ]
                ]
                await self._cache.set(key, pseudo, ttl_for_timeframe(timeframe))
                with_context(logger).info(
                    "market_data.multi_tf.fetched",
                    symbol=symbol.value,
                    tf=timeframe,
                    cache_hit=False,
                    source="ws",
                )
                return timeframe, pseudo

        async with self._semaphore:
            ohlcv: list[list[float]] = await self._exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=self._limit,
            )
        await self._cache.set(key, ohlcv, ttl_for_timeframe(timeframe))
        with_context(logger).info(
            "market_data.multi_tf.fetched",
            symbol=symbol.value,
            tf=timeframe,
            cache_hit=False,
            source="rest",
        )
        return timeframe, ohlcv


__all__ = ["MultiTimeframeFetcher", "ttl_for_timeframe"]
