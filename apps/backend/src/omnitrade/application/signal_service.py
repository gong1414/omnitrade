"""SignalService — per-cycle indicator computation + batch persist.

Sits between ``trading_loop.observe_market`` and ``trading_loop.think``.
Compute is pure (delegated to ``domain.services.indicator_calculator``);
this service adds DB I/O, observability, and the error boundary.

Failure policy (plan v3 MF-6): any exception from the inner compute /
repo path is **swallowed** with ``try/except Exception`` and logged —
it MUST NOT cascade into the trading loop (indicators are best-effort
enrichment, not a trading input in this phase). Do **not** use
``asyncio.shield`` — the planner explicitly rejected it.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import TradingSignal
from omnitrade.domain.services.indicator_calculator import compute_signals
from omnitrade.infrastructure.persistence.repositories.signal_repository import (
    SignalRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


class SignalService:
    """Application service: compute + persist ``TradingSignal`` per cycle."""

    def __init__(
        self,
        *,
        repo: SignalRepository,
        session_factory: SessionFactory,
    ) -> None:
        self._repo = repo
        self._session_factory = session_factory

    async def record_batch(
        self,
        ohlcv_per_symbol: dict[str, list[list[float]]],
        timestamp: datetime,
    ) -> int:
        """Compute + persist a ``TradingSignal`` row for each symbol.

        Args:
            ohlcv_per_symbol: ``{symbol -> OHLCV candles}``; each candle
                is ``[ts_ms, open, high, low, close, volume]``.
            timestamp: Row timestamp to stamp on every computed signal.

        Returns:
            Number of rows successfully persisted (0 when the entire
            batch fails — the exception is swallowed and logged).
        """
        if not ohlcv_per_symbol:
            return 0

        computed: list[TradingSignal] = []
        compute_started = time.perf_counter()
        for symbol, ohlcv in ohlcv_per_symbol.items():
            sym_started = time.perf_counter()
            try:
                sig = compute_signals(ohlcv, symbol, timestamp)
            except Exception as exc:  # defensive — compute is pure, but feed shape drifts
                with_context(logger).warning(
                    "signals.compute_failed",
                    symbol=symbol,
                    error=str(exc),
                )
                continue
            sym_latency_ms = (time.perf_counter() - sym_started) * 1000.0
            with_context(logger).info(
                "signals.computed",
                symbol=symbol,
                latency_ms=round(sym_latency_ms, 3),
            )
            computed.append(sig)

        if not computed:
            return 0

        write_started = time.perf_counter()
        written = 0
        try:
            session = await self._session_factory()
            try:
                for sig in computed:
                    await self._repo.create(session, sig)
                    written += 1
                await session.commit()
            finally:
                await session.close()
        except Exception as exc:  # MF-6: swallow, do not shield
            with_context(logger).warning(
                "signals.write_failed",
                error=str(exc),
                computed=len(computed),
                persisted=written,
            )
            return 0
        finally:
            write_latency_ms = (time.perf_counter() - write_started) * 1000.0
            with_context(logger).info(
                "signals.write.latency_ms",
                latency_ms=round(write_latency_ms, 3),
                rows=written,
                total_latency_ms=round((time.perf_counter() - compute_started) * 1000.0, 3),
            )

        return written


__all__ = ["SessionFactory", "SignalService"]
