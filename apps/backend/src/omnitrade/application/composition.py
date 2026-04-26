"""``build_trading_monitor`` — compose the production ``TradingLoopMonitor``.

This is the single seam that wires the full production cycle:

  * ``observe``  — real REST balances + positions via ``ExchangeClient``.
  * ``news``     — stub (empty list) until the news fetcher is wired.
  * ``think``    — the Agno Agent driven by DeepSeek + MultiMCPTools,
    emitting a ``Decision`` via the DecisionRecorder pattern.
  * ``risk``     — pass-through (risk gating is additive; plugged in later).
  * ``execute``  — dispatch the ``Decision.action`` to ``PositionManager``.
  * ``reflect``  — no-op (RAG layer plugs in later).

No routing logic lives here — ``build_agno_think_fn`` owns the tool-call
loop inside the Agno Agent. This module is purely DI wiring.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.agents.prompts.system import format_system_prompt
from omnitrade.agents.prompts.think import THINK_USER_TEMPLATE
from omnitrade.api.container import ApiContainer
from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
from omnitrade.config import Settings
from omnitrade.domain.entities import (
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.errors import PyramidViolationError
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.indicators import (
    Snapshot,
    compute_ema,
    snapshot_from_ohlcv,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Strategy-desc helper — injected into the minimal system prompt.
# ---------------------------------------------------------------------------

_STRATEGY_DESCRIPTIONS: dict[StrategyName, str] = {
    StrategyName.AI_AUTONOMOUS: (
        "Playbook: single-path trend-follower. Take the cleanest directional "
        "bias across 1H/4H EMAs and trade it with conviction."
    ),
    StrategyName.ALPHA_BETA: (
        "Playbook: dual-signal — trend AND momentum must agree for full "
        "conviction. Divergence means act on the stronger signal at reduced "
        "size, NEVER abstain on disagreement alone."
    ),
}


def _strategy_desc(strategy: StrategyName) -> str:
    return _STRATEGY_DESCRIPTIONS.get(strategy, "")


# ---------------------------------------------------------------------------
# Observe — real REST fetch of tickers + balance + positions.
# ---------------------------------------------------------------------------


async def _exchange_observe(
    container: ApiContainer,
    symbols: list[str],
) -> MarketSnapshot:
    """Pull balance + per-symbol tickers + positions via the exchange."""
    exchange = container.exchange
    balance = await exchange.fetch_balance()
    positions = await exchange.fetch_positions()

    tickers: dict[str, Decimal] = {}
    for raw_sym in symbols:
        try:
            sym = Symbol(value=raw_sym)
        except (ValueError, TypeError) as exc:
            with_context(logger).warning(
                "composition.observe.skip_symbol",
                symbol=raw_sym,
                error=str(exc),
            )
            continue
        try:
            ticker_raw = await exchange.fetch_ticker(sym)
        except Exception as exc:
            with_context(logger).warning(
                "composition.observe.ticker_failed",
                symbol=raw_sym,
                error=str(exc),
            )
            continue
        # ccxt returns ``{"last": <float>, ...}``. Coerce to Decimal via str
        # for precision parity with the rest of the pipeline.
        last = ticker_raw.get("last") if isinstance(ticker_raw, dict) else None
        if last is None:
            continue
        tickers[raw_sym] = Decimal(str(last))

    return MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=list(tickers.keys()) if tickers else list(symbols),
        tickers=tickers,
        positions=list(positions),
        account=balance,
    )


# ---------------------------------------------------------------------------
# News — stub for now (best-effort; the trading loop treats failures as []).
# ---------------------------------------------------------------------------


async def _news_gather() -> list[NewsItem]:
    return []


# ---------------------------------------------------------------------------
# Think — render messages + drive the graph.
# ---------------------------------------------------------------------------


_SAFE_BLOCK_EN = "(no data)"

# Per-cycle budget for the enriched market block; when the fetch + indicator
# compute overruns this we fall through to the legacy ticker-only view so
# the LLM call still happens within ``TRADING_INTERVAL_MINUTES``.
_MARKET_BLOCK_TIMEOUT_SECONDS: float = 30.0


def _render_market_block(market: MarketSnapshot) -> str:
    """Legacy ticker-only block — fallback when the indicator path fails."""
    if not market.tickers:
        return _SAFE_BLOCK_EN
    pairs = [f"{sym}: {price}" for sym, price in sorted(market.tickers.items())]
    return " / ".join(pairs)


def _fmt_price(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_optional_price(value: float | None) -> str:
    return _fmt_price(value) if value is not None else "—"


def _render_market_block_with_indicators(
    market: MarketSnapshot,
    snapshots: list[tuple[Snapshot, float | None, float | None]],
) -> str:
    """Render a rich market block that pairs tickers with indicator readings.

    ``snapshots`` is ``[(snap_15m, ema20_1h, ema20_4h), ...]`` — higher-TF
    EMA20 values are pre-computed by the caller because the 15m snapshot
    carries only the primary TF fields. Symbols that failed indicator
    computation fall through to the ticker-only line.
    """
    if not snapshots:
        return _render_market_block(market)

    lines: list[str] = [
        "| Symbol | Price | 15m EMA20/50/200 | 15m RSI14 | 15m MACD(hist) | "
        "15m ATR14 | Volx | 1h EMA20 | 4h EMA20 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for snap, ema20_1h, ema20_4h in snapshots:
        ema_cell = (
            f"{_fmt_price(snap['ema20'])}/{_fmt_price(snap['ema50'])}/"
            f"{_fmt_optional_price(snap.get('ema200'))}"
        )
        lines.append(
            f"| {snap['symbol']} | {_fmt_price(snap['price'])} | {ema_cell} | "
            f"{snap['rsi14']:.1f} | {snap['macd']:+.3f} | "
            f"{snap['atr14']:.2f} | {snap['volume_ratio']:.2f}x | "
            f"{_fmt_optional_price(ema20_1h)} | {_fmt_optional_price(ema20_4h)} |"
        )

    lines.append("")
    lines.append("Recent 15m closes (newest last):")
    for snap, _e1h, _e4h in snapshots:
        closes = snap.get("recent_closes", [])
        closes_str = ", ".join(f"{c:.1f}" for c in closes[-20:])
        lines.append(f"- {snap['symbol']}: [{closes_str}]")

    return "\n".join(lines)


async def _build_market_block(
    container: ApiContainer,
    market: MarketSnapshot,
) -> str:
    """Fetch multi-TF OHLCV, compute 15m snapshots, render the rich block.

    Wraps the whole fetch+compute path in ``asyncio.wait_for`` so a slow
    exchange leg cannot blow through the cycle cadence. On any failure
    (timeout, partial-fetch shortage, etc.) we degrade gracefully to the
    legacy ticker-only block — the LLM then sees less context rather
    than nothing.
    """
    symbols = list(market.tickers.keys()) or list(market.symbols)
    if not symbols:
        return _render_market_block(market)

    fetcher = container.multi_tf_fetcher
    try:
        ohlcv_map = await asyncio.wait_for(
            fetcher.fetch_ohlcv_multi_tf(symbols, timeframes=["15m", "1h", "4h"]),
            timeout=_MARKET_BLOCK_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        with_context(logger).warning(
            "composition.market_block.timeout",
            symbols=symbols,
            timeout_s=_MARKET_BLOCK_TIMEOUT_SECONDS,
            error=str(exc),
        )
        return _render_market_block(market)
    except Exception as exc:  # degrade gracefully, never nuke the cycle
        with_context(logger).warning(
            "composition.market_block.fetch_failed",
            symbols=symbols,
            error=str(exc),
        )
        return _render_market_block(market)

    snapshots: list[tuple[Snapshot, float | None, float | None]] = []
    for sym in symbols:
        per_tf = ohlcv_map.get(sym) or {}
        ohlcv_15m = per_tf.get("15m") or []
        if len(ohlcv_15m) < 50:
            with_context(logger).info(
                "composition.market_block.insufficient_history",
                symbol=sym,
                candles=len(ohlcv_15m),
            )
            continue
        try:
            snap = snapshot_from_ohlcv(sym, ohlcv_15m)
        except ValueError as exc:
            with_context(logger).warning(
                "composition.market_block.snapshot_failed",
                symbol=sym,
                error=str(exc),
            )
            continue
        closes_1h = [row[4] for row in (per_tf.get("1h") or [])]
        closes_4h = [row[4] for row in (per_tf.get("4h") or [])]
        ema20_1h = compute_ema(closes_1h, 20) if len(closes_1h) >= 20 else None
        ema20_4h = compute_ema(closes_4h, 20) if len(closes_4h) >= 20 else None
        snapshots.append((snap, ema20_1h, ema20_4h))

    if not snapshots:
        return _render_market_block(market)
    return _render_market_block_with_indicators(market, snapshots)


def _render_positions_block(positions: list[Position]) -> str:
    if not positions:
        return _SAFE_BLOCK_EN
    lines: list[str] = []
    for pos in positions:
        pnl = pos.unrealized_pnl if pos.unrealized_pnl is not None else Decimal(0)
        lines.append(
            f"- {pos.symbol} {pos.side} qty={pos.quantity} entry={pos.entry_price} "
            f"cur={pos.current_price} lev={pos.leverage}x uPnL={pnl}"
        )
    return "\n".join(lines)


def _render_account_block(market: MarketSnapshot) -> str:
    account = market.account
    if account is None:
        return _SAFE_BLOCK_EN
    return (
        f"total={account.total_value} available={account.available_cash} "
        f"unrealized={account.unrealized_pnl} realized={account.realized_pnl} "
        f"return_pct={account.return_percent}"
    )


def _render_news_block(news: list[NewsItem]) -> str:
    if not news:
        return _SAFE_BLOCK_EN
    return "\n".join(
        f"- [{item.source}] {item.headline}" for item in news
    )


def _render_think_messages(
    strategy: StrategyName,
    market: MarketSnapshot,
    news: list[NewsItem],
    positions: list[Position],
    settings: Settings,
    iteration: int,
    minutes_elapsed: int,
    market_data_block: str | None = None,
    recent_trades_block: str | None = None,
) -> list[dict[str, Any]]:
    """Build system + user messages for the think LLM call.

    Args:
        market_data_block: Pre-rendered market block. When ``None`` the
            legacy ticker-only block is rendered inline so unit tests
            that call this helper directly stay byte-identical to the
            pre-D1 behaviour.
        recent_trades_block: Pre-rendered recent-cycles feedback block
            (PR-D Phase D3). ``None`` falls back to the legacy placeholder
            so older callers keep working.
    """
    system = format_system_prompt(
        strategy,
        strategy_desc=_strategy_desc(strategy),
        extreme_stop_loss_percent=int(abs(settings.extreme_stop_loss_percent)),
        max_holding_hours=settings.max_holding_hours,
        max_leverage=settings.max_leverage,
        max_positions=settings.max_positions,
    )
    block = market_data_block if market_data_block is not None else _render_market_block(market)
    user = THINK_USER_TEMPLATE.format(
        iteration=iteration,
        current_time=market.timestamp.isoformat(),
        market_data_block=block,
        news_block=_render_news_block(news),
        account_block=_render_account_block(market),
        positions_block=_render_positions_block(positions),
        strategy_banner="",
        hard_risk_floor="",
        tactical_box="",
        decision_flow="",
        external_block=_SAFE_BLOCK_EN,
        sharpe_block="",
        recent_trades_block=(
            recent_trades_block if recent_trades_block is not None else _SAFE_BLOCK_EN
        ),
        interval_minutes=settings.trading_interval_minutes,
        minutes_elapsed=minutes_elapsed,
        output_language="zh",
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _build_base_think_fn(
    container: ApiContainer,
    settings: Settings,
) -> Callable[[MarketSnapshot, list[NewsItem]], Any]:
    """Return the production ``ThinkFn`` bound to ``container``.

    The Agno Agent owns its DeepSeek model + MultiMCPTools toolkit, so no
    separate ``LLMClient`` is needed at this seam.
    """
    from omnitrade.agents.knowledge import build_trade_journal_knowledge
    from omnitrade.agents.trading_agent import build_agno_think_fn

    try:
        strategy = StrategyName(settings.trading_strategy)
    except ValueError:
        with_context(logger).warning(
            "composition.unknown_strategy_fallback",
            strategy=settings.trading_strategy,
        )
        strategy = StrategyName.AI_AUTONOMOUS

    # T10: build the trade-journal RAG handle once at composition time.
    # Returns ``None`` (with an info-level skip log) when Postgres is
    # unwired or the embedder credentials are missing — the Agent then
    # runs without RAG memory rather than failing the cycle.
    knowledge = build_trade_journal_knowledge(settings)

    with_context(logger).info(
        "composition.think_fn_built",
        strategy=str(strategy),
        model=settings.agno_llm_model,
        knowledge_enabled=knowledge is not None,
    )
    think_fn = build_agno_think_fn(
        container,
        settings,
        render_messages=_render_think_messages,
        strategy=strategy,
        market_block_builder=_build_market_block,
        recent_trades_block_builder=_render_recent_trades_block,
        # T3: forward the event bus so the G5 QA-phrase post_hook can
        # publish ``EVENT_ORCHESTRATOR_ERROR`` when the LLM reports a
        # data-quality fault (auto-lights the dashboard banner).
        event_bus=container.event_bus,
        # T9: forward the HITL approval registry so the trading agent
        # can pause large opens for operator approval via the dashboard
        # banner. ``None`` paths in tests fall through to auto-reject.
        approval_registry=getattr(container, "approval_registry", None),
        # T10: pass the optional Knowledge handle so Agno can auto-inject
        # relevant prior cycles into the system prompt.
        knowledge=knowledge,
    )
    # Surface the knowledge handle on the think-fn so the monitor can
    # ingest decisions back into the same instance (single source of
    # truth: the Agent reads + writes through the same handle).
    think_fn.knowledge = knowledge  # type: ignore[attr-defined]
    return think_fn


# ---------------------------------------------------------------------------
# Execute — dispatch Decision.action → PositionManager.
# ---------------------------------------------------------------------------


def _build_execute_fn(
    container: ApiContainer,
    settings: Settings,
) -> Callable[[Decision], Any]:
    """Return an ``ExecuteFn`` that dispatches to ``PositionManager``.

    The trading-loop contract requires ``ExecuteFn`` to return a list of
    ``Trade``s (possibly empty). ``hold`` / ``close`` with no open position
    / malformed decisions all safely return ``[]``.
    """
    pm = container.position_manager

    async def execute(decision: Decision) -> list[Trade]:
        action = decision.action
        # Exchange errors (e.g. Gate contract-unit rejection, insufficient
        # balance, rate limits) must NOT nuke the whole cycle — otherwise the
        # AgentDecision with its structured reasoning never gets recorded.
        # We log + swallow and return [] so downstream `reflect` + monitor
        # `record()` still run. The decision carries its reasoning to the UI.
        try:
            if action == "open":
                if decision.symbol is None or decision.side is None:
                    with_context(logger).warning(
                        "composition.execute.open_missing_fields",
                        symbol=decision.symbol,
                        side=decision.side,
                    )
                    return []
                size = decision.size or settings.default_position_size
                leverage = decision.leverage or settings.default_leverage
                with_context(logger).info(
                    "composition.execute.open",
                    symbol=decision.symbol,
                    side=decision.side,
                    size=str(size),
                    leverage=leverage,
                )
                trade = await pm.open_position(
                    symbol=decision.symbol,
                    side=decision.side,
                    size=size,
                    leverage=leverage,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                    confidence=decision.confidence,
                )
                return [trade]
            if action == "close":
                if decision.symbol is None:
                    return []
                trade = await pm.close_position(symbol=decision.symbol, reason="ai_decision")
                return [trade]
            if action == "partial_close":
                if decision.symbol is None or decision.close_percentage is None:
                    return []
                trade = await pm.partial_close(
                    symbol=decision.symbol,
                    percentage=decision.close_percentage,
                    reason="ai_decision",
                )
                return [trade]
            # hold — no-op.
            return []
        except PyramidViolationError as exc:
            # Alpha Arena no-pyramid rule tripped. Log + swallow so the
            # cycle's StructuredReason still records — the LLM sees the
            # existing position in the next cycle's positions_block and
            # can decide to close first.
            with_context(logger).warning(
                "composition.execute.pyramid_violation",
                action=action,
                symbol=decision.symbol,
                error=str(exc),
            )
            return []
        except Exception as exc:  # exchange/ccxt errors must not kill cycle
            with_context(logger).warning(
                "composition.execute.exchange_error",
                action=action,
                symbol=decision.symbol,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return []

    return execute


# ---------------------------------------------------------------------------
# Risk / reflect — pass-through stubs (hookable later).
# ---------------------------------------------------------------------------


async def _render_recent_trades_block(container: ApiContainer) -> str:
    """Render the last 5 decisions as a feedback block for LLM self-reflection.

    Format (newest first):
      Recent cycles (most-recent first):
      - Cycle #23 (2 min ago): open confidence=0.75 — <short market_context>
      - Cycle #22 (4 min ago): hold confidence=0.35 — <short market_context>
      ...

    Falls back to an explicit "no prior decisions yet" line on empty DB so
    the prompt never has a dangling header. LLM can now reference its own
    behaviour across cycles (PR-D Phase D3 closes the feedback-loop gap).
    """
    try:
        session = await container.open_session()
        try:
            recent = await container.decision_repo.list_recent_for_feedback(
                session, limit=5
            )
        finally:
            await session.close()
    except Exception as exc:
        with_context(logger).warning(
            "composition.recent_trades_block_failed", error=str(exc)
        )
        return "Recent cycles: (feedback unavailable this cycle)"

    if not recent:
        return "Recent cycles: no prior decisions yet."

    now = datetime.now(UTC)
    lines: list[str] = ["Recent cycles (most-recent first):"]
    for d in recent:
        ts = d.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age_min = max(0, int((now - ts).total_seconds() / 60))
        conf = (
            f"{d.structured_confidence:.2f}"
            if d.structured_confidence is not None
            else "—"
        )
        brief = (d.market_context or "").strip().replace("\n", " ")
        if len(brief) > 160:
            brief = brief[:157] + "..."
        brief_tail = f" — {brief}" if brief else ""
        lines.append(
            f"- Cycle #{d.iteration} ({age_min} min ago): "
            f"{d.decision} confidence={conf}{brief_tail}"
        )
    return "\n".join(lines)


def _build_risk_check_fn(
    container: ApiContainer,
    settings: Settings,
) -> Callable[[Decision, list[Position]], Any]:
    """Return a RiskCheckFn that force-holds when daily loss cap breached.

    Wraps :class:`DailyLossLimiter`: once today's realized PnL drops below
    ``-settings.daily_loss_cap_usdt`` any open/close/partial_close request
    is rewritten to ``hold`` with a log warning. ``hold`` decisions pass
    through untouched (the cap never *forces* action, only vetoes it).
    PR-D Phase D3 account-level kill-switch.
    """
    from omnitrade.application.risk_service import DailyLossCap, DailyLossLimiter

    cap = DailyLossCap(cap_usdt=Decimal(str(settings.daily_loss_cap_usdt)))
    limiter = DailyLossLimiter(
        trade_repo=container.trade_repo,
        session_factory=container.open_session,
        cap=cap,
    )

    async def risk_check(decision: Decision, _positions: list[Position]) -> Decision:
        if decision.action == "hold":
            return decision
        try:
            breached = await limiter.check()
        except Exception as exc:
            with_context(logger).warning(
                "composition.risk.daily_loss_check_failed", error=str(exc)
            )
            return decision
        if breached:
            with_context(logger).warning(
                "composition.risk.daily_loss_cap_triggered",
                cap_usdt=str(cap.cap_usdt),
                requested_action=decision.action,
                symbol=decision.symbol,
            )
            return decision.model_copy(update={"action": "hold"})
        return decision

    return risk_check


async def _risk_check(decision: Decision, _positions: list[Position]) -> Decision:
    """Legacy pass-through used by unit tests that don't need the limiter."""
    return decision


async def _reflect_fn(_decision: Decision, _trades: list[Trade]) -> None:
    return None


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

_DEFAULT_SYMBOLS: tuple[str, ...] = ("BTC_USDT", "ETH_USDT")


def _resolve_symbols(settings: Settings) -> list[str]:
    """Return the configured ``trading_symbols`` or the sane default pair."""
    raw = getattr(settings, "trading_symbols", None)
    if isinstance(raw, list) and raw:
        return [str(s) for s in raw]
    return list(_DEFAULT_SYMBOLS)


def build_trading_monitor(
    container: ApiContainer,
    settings: Settings,
) -> TradingLoopMonitor:
    """Compose the production ``TradingLoopMonitor``.

    This is the seam ``main.lifespan`` calls when SCHEDULER_ENABLED=true AND
    LLM credentials are present. The Agno Agent owns its own model — no
    separate ``LLMClient`` injection is needed here.
    """
    symbols = _resolve_symbols(settings)

    async def observe() -> MarketSnapshot:
        return await _exchange_observe(container, symbols)

    base_think = _build_base_think_fn(container, settings)
    execute = _build_execute_fn(container, settings)
    risk_check = _build_risk_check_fn(container, settings)

    # T10: surface the trade-journal Knowledge handle (if any) on the
    # monitor so the post-cycle ingest hook lands rows in the same
    # PgVector-backed table the Agent searches against. ``getattr``
    # with default keeps non-Agno think-fn paths (e.g. legacy stubs in
    # tests that build the monitor directly) compatible.
    knowledge_handle = getattr(base_think, "knowledge", None)

    return TradingLoopMonitor(
        interval_minutes=settings.trading_interval_minutes,
        exchange_observe=observe,
        news_gather=_news_gather,
        think_fn=base_think,
        risk_check=risk_check,
        execute_fn=execute,
        reflect_fn=_reflect_fn,
        decision_service=container.decision_service,
        ws_client=container.ws_client,
        use_ws_market_data=settings.use_ws_market_data,
        cassette_mode=settings.cassette_mode,
        knowledge=knowledge_handle,
    )


__all__ = ["build_trading_monitor"]
