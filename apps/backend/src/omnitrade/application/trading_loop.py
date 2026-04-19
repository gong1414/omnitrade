"""Outer trading loop — pure asyncio orchestration (no langgraph import).

Per consensus plan §6 Phase 4.1, the outer loop composes five plain
``async def`` steps and calls into the LangGraph ``think`` node at the
``think()`` boundary. LangGraph is ONLY imported from
``agents/think_node.py``; this module must stay framework-free at the
graph level.

Deterministic fan-out (§3 P3 / §10 Changelog #20): ``observe_market`` and
``gather_news`` run concurrently via ``asyncio.gather(..., return_exceptions
=True)`` and results are merged in a canonical sorted order before being
fed into ``think``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.domain.entities import (
    AccountSnapshot,
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)
from omnitrade.infrastructure.market_data.ws_client import TickerUpdate, WSClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


# ── Callable protocols (Callable type-aliases keep this module free of
#    heavy dependencies so tests can wire in-memory stubs.) ───────────── #

ExchangeObserveFn = Callable[[], Awaitable[MarketSnapshot]]
NewsGatherFn = Callable[[], Awaitable[list[NewsItem]]]
ThinkFn = Callable[[MarketSnapshot, list[NewsItem]], Awaitable[Decision]]
RiskCheckFn = Callable[[Decision, list[Position]], Awaitable[Decision]]
ExecuteFn = Callable[[Decision], Awaitable[list[Trade]]]
ReflectFn = Callable[[Decision, list[Trade]], Awaitable[None]]


@dataclass
class LoopOutcome:
    """Result of a single trading-loop cycle."""

    decision: Decision
    trades: list[Trade]
    market: MarketSnapshot
    news: list[NewsItem]
    started_at: datetime
    finished_at: datetime
    # Per-stage wall-clock cost in milliseconds. Six keys mirror the
    # PipelineStatus rail (observe / news / think / decide / execute /
    # reflect) so the frontend can animate each segment proportionally
    # instead of falling back to a hardcoded setTimeout ladder.
    stage_ms: dict[str, float] = field(default_factory=dict)


# ── step 1 — observe_market ──────────────────────────────────────────── #


def _canonical_ws_buffer_hash(snapshot: dict[str, TickerUpdate]) -> str:
    """Return a deterministic sha256 of the WS buffer snapshot.

    The snapshot dict is serialised with sorted keys + fixed field order
    so that two logically-equal buffers always hash the same regardless
    of insertion order. Used by ``observe_market`` to produce the
    transient ``MarketSnapshot.ws_buffer_hash`` fingerprint (G-6).
    """
    canonical = [
        {
            "symbol": sym,
            "price": snapshot[sym].price,
            "timestamp_ms": snapshot[sym].timestamp_ms,
            "volume_24h": snapshot[sym].volume_24h,
        }
        for sym in sorted(snapshot)
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def observe_market(
    exchange_observe: ExchangeObserveFn,
    ws_client: WSClient | None = None,
    *,
    cassette_mode: bool = False,
) -> MarketSnapshot:
    """Pull a fresh ``MarketSnapshot`` via the injected exchange fn.

    WS→cycle determinism contract (Phase 8.6, MAJOR-5):

    1. A ``WSClient`` is a persistent background connection that buffers
       ``TickerUpdate`` events per symbol.
    2. When ``ws_client is not None`` AND ``cassette_mode`` is False, we
       take a shallow snapshot of the WS buffer on entry and attach
       ``sha256(canonical_json(snapshot))`` to the returned
       ``MarketSnapshot.ws_buffer_hash``. The field is transient and
       MUST NOT be persisted to ``agent_decisions.market_analysis`` (G-6).
    3. ``run_cycle`` downstream reads only the frozen ``MarketSnapshot``
       — it never reads the live WS buffer again.
    4. ``cassette_mode=True`` FORCES the REST path: any supplied
       ``ws_client`` is ignored so cassette byte-replay stays
       deterministic.
    5. The monitor (``application/monitors/trading_loop_monitor.py``)
       enforces a startup assertion that ``USE_WS_MARKET_DATA`` and
       ``CASSETTE_MODE`` are never simultaneously true (CRITICAL-1).
    """
    with_context(logger).info(
        "trading_loop.observe_market",
        has_ws=ws_client is not None,
        cassette_mode=cassette_mode,
    )
    snapshot = await exchange_observe()
    if ws_client is not None and not cassette_mode:
        buf = ws_client.buffer_snapshot()
        if buf:
            return snapshot.model_copy(update={"ws_buffer_hash": _canonical_ws_buffer_hash(buf)})
    return snapshot


# ── step 2 — gather_news ─────────────────────────────────────────────── #


async def gather_news(news_gather: NewsGatherFn) -> list[NewsItem]:
    """Pull news items; empty list on any exception (non-fatal)."""
    with_context(logger).info("trading_loop.gather_news")
    try:
        return await news_gather()
    except Exception as exc:  # news is best-effort
        with_context(logger).warning("trading_loop.gather_news_failed", error=str(exc))
        return []


# ── step 3 — think (LangGraph boundary; consumes sorted fan-out) ─────── #


async def think(
    think_fn: ThinkFn,
    market: MarketSnapshot,
    news: list[NewsItem],
) -> Decision:
    """Call the LangGraph think node with canonically-ordered inputs.

    Sort news newest-first and symbols alphabetically so fan-out results
    from ``asyncio.gather`` don't leak scheduling order into the prompt
    (§10 Changelog #20 — Critic Should-Fix-1).
    """
    sorted_news = sorted(news, key=lambda n: (n.published_at, n.headline), reverse=True)
    sorted_symbols = sorted(market.symbols)
    sorted_market = market.model_copy(update={"symbols": sorted_symbols})
    with_context(logger).info(
        "trading_loop.think",
        n_symbols=len(sorted_symbols),
        n_news=len(sorted_news),
    )
    return await think_fn(sorted_market, sorted_news)


# ── step 4 — validate_decision (risk checks) ────────────────────────── #


async def validate_decision(
    risk_check: RiskCheckFn,
    decision: Decision,
    positions: list[Position],
) -> Decision:
    """Apply risk checks; returns a possibly-overridden Decision (e.g. force HOLD)."""
    with_context(logger).info("trading_loop.validate_decision", action=decision.action)
    return await risk_check(decision, positions)


# ── step 5 — execute_trades ─────────────────────────────────────────── #


async def execute_trades(execute_fn: ExecuteFn, decision: Decision) -> list[Trade]:
    """Dispatch the decision via the execute adapter; returns executed trades."""
    with_context(logger).info("trading_loop.execute_trades", action=decision.action)
    if decision.action == "hold":
        return []
    return await execute_fn(decision)


# ── step 6 — reflect (append to RAG) ────────────────────────────────── #


async def reflect(
    reflect_fn: ReflectFn,
    decision: Decision,
    trades: list[Trade],
) -> None:
    """Feed the decision/trade outcome into the vector-store RAG layer."""
    with_context(logger).info("trading_loop.reflect", n_trades=len(trades))
    await reflect_fn(decision, trades)


# ── orchestrator: run one full cycle ────────────────────────────────── #


async def run_cycle(
    *,
    exchange_observe: ExchangeObserveFn,
    news_gather: NewsGatherFn,
    think_fn: ThinkFn,
    risk_check: RiskCheckFn,
    execute_fn: ExecuteFn,
    reflect_fn: ReflectFn,
    signal_service: Any | None = None,
    ws_client: WSClient | None = None,
    cassette_mode: bool = False,
) -> LoopOutcome:
    """Run a single trading-loop cycle end-to-end.

    Deterministic fan-out: ``observe_market`` and ``gather_news`` launch
    concurrently; results are ordered canonically before ``think`` is
    called. Exceptions from ``gather_news`` are swallowed (best-effort),
    exceptions from ``observe_market`` propagate (a market snapshot is
    required to make any decision).

    Phase 8.2: when ``signal_service`` is provided AND ``market_snapshot``
    carries ``multi_tf_ohlcv``, a best-effort ``record_batch`` call writes
    ``TradingSignal`` rows between observe and think. Failures are
    swallowed inside the service (plan v3 MF-6); the trading loop always
    proceeds. Default ``None`` preserves byte-exact cassette replay.
    """
    started_at = datetime.now(tz=UTC)
    stage_ms: dict[str, float] = {}

    fanout_t0 = time.perf_counter()
    market_task = asyncio.create_task(
        observe_market(exchange_observe, ws_client, cassette_mode=cassette_mode)
    )
    news_task = asyncio.create_task(gather_news(news_gather))

    # Concurrent fan-out; gather(..., return_exceptions=True) never raises —
    # exceptions are returned in the result tuple.
    raw: tuple[Any, Any] = await asyncio.gather(market_task, news_task, return_exceptions=True)
    market_result, news_result = raw
    fanout_ms = (time.perf_counter() - fanout_t0) * 1000.0
    # observe + news ran in parallel — attribute half each so the UI
    # shows both segments without inventing extra duration.
    stage_ms["observe"] = fanout_ms / 2.0
    stage_ms["news"] = fanout_ms / 2.0

    if isinstance(market_result, BaseException):
        raise market_result
    if not isinstance(market_result, MarketSnapshot):
        raise TypeError(
            f"observe_market returned {type(market_result).__name__}, expected MarketSnapshot"
        )
    market_snapshot: MarketSnapshot = market_result

    news_items: list[NewsItem]
    if isinstance(news_result, BaseException) or not isinstance(news_result, list):
        news_items = []
    else:
        news_items = list(news_result)

    if signal_service is not None and market_snapshot.multi_tf_ohlcv:
        # Flatten per-symbol multi-TF map to a single representative TF
        # (prefer 1h, fall back to the first TF key that yields non-empty
        # candles). Record is best-effort — SignalService swallows its
        # own exceptions, but we also guard here in case the picker
        # misbehaves on malformed input.
        ohlcv_per_symbol: dict[str, list[list[float]]] = {}
        for sym, tf_map in market_snapshot.multi_tf_ohlcv.items():
            chosen: list[list[float]] | None = tf_map.get("1h")
            if not chosen:
                for candles in tf_map.values():
                    if candles:
                        chosen = candles
                        break
            if chosen:
                ohlcv_per_symbol[sym] = chosen
        if ohlcv_per_symbol:
            try:
                await signal_service.record_batch(
                    ohlcv_per_symbol, market_snapshot.timestamp
                )
            except Exception as exc:
                with_context(logger).warning(
                    "trading_loop.signal_record_failed", error=str(exc)
                )

    t0 = time.perf_counter()
    decision = await think(think_fn, market_snapshot, news_items)
    stage_ms["think"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    validated = await validate_decision(risk_check, decision, list(market_snapshot.positions))
    stage_ms["decide"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    trades = await execute_trades(execute_fn, validated)
    stage_ms["execute"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    await reflect(reflect_fn, validated, trades)
    stage_ms["reflect"] = (time.perf_counter() - t0) * 1000.0

    finished_at = datetime.now(tz=UTC)
    return LoopOutcome(
        decision=validated,
        trades=trades,
        market=market_snapshot,
        news=news_items,
        started_at=started_at,
        finished_at=finished_at,
        stage_ms=stage_ms,
    )


# ── helpers shared with tests / application layer ───────────────────── #


def make_empty_account_snapshot(total_value: Decimal = Decimal(0)) -> AccountSnapshot:
    """Convenience factory used by stubs and tests."""
    return AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=total_value,
        available_cash=total_value,
        unrealized_pnl=Decimal(0),
        realized_pnl=Decimal(0),
        return_percent=Decimal(0),
    )


__all__ = [
    "ExchangeObserveFn",
    "ExecuteFn",
    "LoopOutcome",
    "NewsGatherFn",
    "ReflectFn",
    "RiskCheckFn",
    "ThinkFn",
    "execute_trades",
    "gather_news",
    "make_empty_account_snapshot",
    "observe_market",
    "reflect",
    "run_cycle",
    "think",
    "validate_decision",
]
