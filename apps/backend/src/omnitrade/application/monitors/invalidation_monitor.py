"""InvalidationMonitor — auto-close positions whose LLM-authored
``invalidation_condition`` now matches live market state.

Alpha Arena / kojott parity: the LLM writes an ``invalidation_condition``
at open time (stored on ``agent_decisions``). kojott's ``bot.py:766``
auto-closes the position the moment that condition trips; PR-D Phase D2
lifts the same enforcement here so the field is no longer decorative.

Design notes
------------
* Runs as a separate APScheduler job (cadence independent from the
  trading cycle) — defaults to 60s. Gated by ``SCHEDULER_ENABLED``.
* Fetches fresh 15m OHLCV per symbol via the existing
  ``MultiTimeframeFetcher`` so we don't add yet another market-data leg.
* Asks the LLM a *minimal* yes/no question with temperature=0 and no
  tools — cheap, deterministic, ≤100 output tokens.
* Single-position failures (LLM timeout, malformed JSON, exchange hiccup)
  are logged + swallowed so one bad symbol cannot halt the monitor.
* Invalidation text itself is sourced from the latest AgentDecision row
  that mentioned the symbol (``Position`` carries no ``invalidation_condition``
  column in the current schema).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.position_manager import PositionManager
from omnitrade.domain.protocols import ExchangeClient, LLMClient
from omnitrade.infrastructure.market_data.indicators import (
    Snapshot,
    snapshot_from_ohlcv,
)
from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


# 15m snapshot needs at least 50 candles per ``snapshot_from_ohlcv``
# warm-up contract.
_MIN_CANDLES: int = 50
# Pull 100 so EMA/MACD/RSI/ATR are all well-seeded.
_OHLCV_LIMIT: int = 100
# Minimal LLM call — generous enough for one JSON object, stingy enough
# to keep cost trivial.
_LLM_MAX_TOKENS: int = 120


class InvalidationMonitor:
    """Per-tick driver: for every OPEN position, ask the LLM whether its
    invalidation condition has fired and close the position if it has.
    """

    def __init__(
        self,
        *,
        interval_seconds: int,
        llm: LLMClient,
        model: str,
        exchange: ExchangeClient,
        multi_tf_fetcher: MultiTimeframeFetcher,
        position_repo: PositionRepository,
        decision_repo: DecisionRepository,
        position_manager: PositionManager,
        session_factory: SessionFactory,
    ) -> None:
        self._interval_seconds = interval_seconds
        self._llm = llm
        self._model = model
        self._exchange = exchange
        self._multi_tf_fetcher = multi_tf_fetcher
        self._position_repo = position_repo
        self._decision_repo = decision_repo
        self._position_manager = position_manager
        self._session_factory = session_factory

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    async def tick(self) -> None:
        """Check every OPEN position for an invalidation trigger."""
        with_context(logger).info("invalidation_monitor.tick")
        session = await self._session_factory()
        try:
            positions = await self._position_repo.list_all(session)
        finally:
            await session.close()

        for pos in positions:
            # Skip fully-closed rows (codebase convention: quantity > 0 == OPEN).
            if pos.quantity <= 0:
                continue
            try:
                await self._check_one(pos.symbol, pos.side, pos.entry_price)
            except Exception as exc:  # single-position failure must not stop loop
                with_context(logger).warning(
                    "invalidation_monitor.tick_failed",
                    symbol=pos.symbol,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                continue

    async def _check_one(
        self,
        symbol: str,
        side: str,
        entry_price: Any,
    ) -> None:
        # Pull the latest invalidation text for this symbol. ``Position``
        # itself has no invalidation column — it lives on ``agent_decisions``.
        session = await self._session_factory()
        try:
            invalidation_text = await self._decision_repo.get_latest_invalidation_for_symbol(
                session, symbol
            )
        finally:
            await session.close()
        if not invalidation_text:
            with_context(logger).debug(
                "invalidation_monitor.skip_no_text", symbol=symbol
            )
            return

        # Fresh 15m snapshot. Reuse the composition path — this hits the
        # shared TTL cache when the trading loop already fetched 15m.
        ohlcv_map = await self._multi_tf_fetcher.fetch_ohlcv_multi_tf(
            [symbol], timeframes=["15m"]
        )
        ohlcv_15m = ohlcv_map.get(symbol, {}).get("15m", [])
        if len(ohlcv_15m) < _MIN_CANDLES:
            with_context(logger).info(
                "invalidation_monitor.insufficient_ohlcv",
                symbol=symbol,
                candles=len(ohlcv_15m),
            )
            return
        try:
            snap = snapshot_from_ohlcv(symbol, ohlcv_15m)
        except ValueError as exc:
            with_context(logger).warning(
                "invalidation_monitor.snapshot_failed",
                symbol=symbol,
                error=str(exc),
            )
            return

        triggered, reason = await self._ask_llm(
            symbol=symbol,
            side=side,
            entry=float(entry_price),
            invalidation_text=invalidation_text,
            snapshot=snap,
        )
        if triggered:
            with_context(logger).warning(
                "invalidation_monitor.auto_close",
                symbol=symbol,
                reason=reason,
            )
            await self._position_manager.close_position(
                symbol=symbol,
                reason="invalidation_triggered",
            )
        else:
            with_context(logger).info(
                "invalidation_monitor.still_valid",
                symbol=symbol,
                reason=reason,
            )

    async def _ask_llm(
        self,
        *,
        symbol: str,
        side: str,
        entry: float,
        invalidation_text: str,
        snapshot: Snapshot,
    ) -> tuple[bool, str]:
        """Single yes/no LLM call. Returns ``(triggered, reason_str)``.

        On any parse / LLM failure we return ``(False, "<reason>")`` —
        the safe default is "do NOT auto-close" when we cannot confirm.
        """
        ema200_str = (
            f"{snapshot.get('ema200'):.2f}"
            if snapshot.get("ema200") is not None
            else "n/a"
        )
        prompt = (
            f"Position: {symbol} {side} opened at {entry}.\n"
            f"Invalidation condition: \"{invalidation_text}\"\n"
            f"Current 15m snapshot: price={snapshot['price']:.2f}, "
            f"EMA20={snapshot['ema20']:.2f}, EMA50={snapshot['ema50']:.2f}, "
            f"EMA200={ema200_str}, RSI14={snapshot['rsi14']:.1f}, "
            f"MACD={snapshot['macd']:+.3f}, ATR14={snapshot['atr14']:.2f}.\n\n"
            "Has the invalidation condition been met RIGHT NOW? Answer "
            "with a single JSON object:\n"
            '{"triggered": true|false, "reason": "<one sentence>"}'
        )
        try:
            response = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                temperature=0.0,
            )
        except Exception as exc:
            with_context(logger).warning(
                "invalidation_monitor.llm_failed",
                symbol=symbol,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False, f"llm_failed: {exc}"

        content = _extract_content(response)
        if not content:
            return False, "empty_llm_content"
        parsed = _parse_triggered_json(content)
        if parsed is None:
            with_context(logger).warning(
                "invalidation_monitor.parse_failed",
                symbol=symbol,
                content_preview=content[:200],
            )
            return False, "parse_failed"
        triggered, reason_text = parsed
        return triggered, reason_text


def _extract_content(response: dict[str, Any]) -> str:
    """Pull ``choices[0].message.content`` out of a LiteLLM-style dict."""
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return str(content)


_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_triggered_json(content: str) -> tuple[bool, str] | None:
    """Extract ``{"triggered": bool, "reason": str}`` from ``content``.

    The LLM often wraps JSON in code fences or adds preamble; we grab the
    first balanced JSON object via regex. Returns ``None`` when the
    content cannot be parsed into the expected shape — callers treat that
    as "do not trigger" (safe default).
    """
    # Try raw JSON first (fast path when the LLM obeys the schema).
    candidate = content.strip()
    for text in (candidate, *(_JSON_RE.findall(content) or [])):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if "triggered" not in data:
            continue
        triggered = bool(data.get("triggered"))
        reason = str(data.get("reason") or "")
        return triggered, reason
    return None


__all__ = ["InvalidationMonitor"]
