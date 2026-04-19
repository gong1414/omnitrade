"""BacktestEngine — drives ``run_cycle`` bar-by-bar over historical OHLCV.

Architectural decision (BacktestContainer vs. composition reuse)
-----------------------------------------------------------------
We do NOT instantiate ``ApiContainer``. The production
``composition._build_base_think_fn`` pulls ``decision_repo`` /
``open_session`` / ``position_manager`` off the container — the first
two require a live SQLAlchemy session, which we don't want to spin up
for every backtest run. Instead we assemble the think_fn in place
here, reusing the stable ingredients:

    * ``composition._build_tool_schemas`` — tool JSON schemas
    * ``composition._tool_choice_for_strategy`` — tool_choice policy
    * ``composition._render_think_messages`` — prompt renderer
    * ``agents.think_node.build_think_graph`` / ``invoke_think`` — graph
    * ``infrastructure.market_data.indicators.snapshot_from_ohlcv`` —
      market block indicator builder

The market block is rendered from the ``BacktestExchange`` history
rather than a ``MultiTimeframeFetcher`` — we already have the candles
in memory.

The ``recent_trades_block`` is rebuilt from ``_decisions_so_far`` kept
in the engine (not from a DB), so the LLM still sees its own prior
behaviour across cycles. Pyramiding is avoided by passing positions
into the tool-schema reasoning phase — the engine's execute_fn drops
``open`` calls for symbols with an existing position (same rule as
the production ``PyramidViolationError`` path).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.agents.think_node import (
    ToolRegistry,
    build_think_graph,
    invoke_think,
)
from omnitrade.application.composition import (
    _build_tool_schemas,
    _render_think_messages,
    _tool_choice_for_strategy,
)
from omnitrade.application.trading_loop import LoopOutcome, run_cycle
from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.data_source import HistoricalOHLCV, iso_to_ms, timeframe_to_ms
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.backtest.metrics import compute_metrics
from omnitrade.config import Settings
from omnitrade.domain.entities import (
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient
from omnitrade.infrastructure.market_data.indicators import (
    Snapshot,
    compute_ema,
    snapshot_from_ohlcv,
)

logger = structlog.get_logger(__name__)


# ── BacktestResult ──────────────────────────────────────────────────── #


@dataclass
class BacktestResult:
    """Output of ``BacktestEngine.run`` — equity curve + decisions + trades."""

    symbols: list[str]
    timeframe: str
    start: datetime
    end: datetime
    strategy: str
    initial_balance: Decimal
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    decisions: list[tuple[datetime, Decision]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        return render_markdown(self)


# ── market-block rendering (stripped-down copy of composition path) ── #


def _fmt_price(v: float) -> str:
    return f"{v:,.2f}"


def _fmt_opt(v: float | None) -> str:
    return _fmt_price(v) if v is not None else "—"


def _render_market_block(
    symbols: list[str],
    snapshots: list[tuple[Snapshot, float | None, float | None]],
) -> str:
    """Render the same table shape as the production market block."""
    if not snapshots:
        # Fallback: minimal ticker-only line so the LLM never sees a
        # blank market block (would confuse the gate logic).
        return "(no market data)"
    lines: list[str] = [
        "| Symbol | Price | 15m EMA20/50/200 | 15m RSI14 | 15m MACD(hist) | "
        "15m ATR14 | Volx | 1h EMA20 | 4h EMA20 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for snap, ema20_1h, ema20_4h in snapshots:
        ema_cell = (
            f"{_fmt_price(snap['ema20'])}/{_fmt_price(snap['ema50'])}/"
            f"{_fmt_opt(snap.get('ema200'))}"
        )
        lines.append(
            f"| {snap['symbol']} | {_fmt_price(snap['price'])} | {ema_cell} | "
            f"{snap['rsi14']:.1f} | {snap['macd']:+.3f} | "
            f"{snap['atr14']:.2f} | {snap['volume_ratio']:.2f}x | "
            f"{_fmt_opt(ema20_1h)} | {_fmt_opt(ema20_4h)} |"
        )
    lines.append("")
    lines.append("Recent 15m closes (newest last):")
    for snap, _e1h, _e4h in snapshots:
        closes = snap.get("recent_closes", [])
        closes_str = ", ".join(f"{c:.1f}" for c in closes[-20:])
        lines.append(f"- {snap['symbol']}: [{closes_str}]")
    return "\n".join(lines)


def _render_recent_trades_block(
    prior: list[tuple[datetime, Decision]], now: datetime
) -> str:
    if not prior:
        return "Recent cycles: no prior decisions yet."
    lines: list[str] = ["Recent cycles (most-recent first):"]
    for idx, (ts, d) in enumerate(reversed(prior[-5:])):
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
        cycle_num = len(prior) - idx
        lines.append(
            f"- Cycle #{cycle_num} ({age_min} min ago): "
            f"{d.action} confidence={conf}{brief_tail}"
        )
    return "\n".join(lines)


async def _build_backtest_market_block(
    exchange: BacktestExchange, symbols: list[str]
) -> str:
    snapshots: list[tuple[Snapshot, float | None, float | None]] = []
    for sym in symbols:
        try:
            from omnitrade.domain.value_objects import Symbol as Sym

            sym_obj = Sym(value=sym)
        except Exception:
            continue
        ohlcv_15m = await exchange.fetch_ohlcv(sym_obj, "15m", 210)
        if len(ohlcv_15m) < 50:
            continue
        try:
            snap = snapshot_from_ohlcv(sym, ohlcv_15m)
        except ValueError:
            continue
        ohlcv_1h = await exchange.fetch_ohlcv(sym_obj, "1h", 30)
        ohlcv_4h = await exchange.fetch_ohlcv(sym_obj, "4h", 30)
        closes_1h = [row[4] for row in ohlcv_1h]
        closes_4h = [row[4] for row in ohlcv_4h]
        ema20_1h = compute_ema(closes_1h, 20) if len(closes_1h) >= 20 else None
        ema20_4h = compute_ema(closes_4h, 20) if len(closes_4h) >= 20 else None
        snapshots.append((snap, ema20_1h, ema20_4h))
    return _render_market_block(symbols, snapshots)


# ── execute / news / risk stubs ─────────────────────────────────────── #


async def _empty_news() -> list[NewsItem]:
    return []


def _build_execute_fn(
    exchange: BacktestExchange,
) -> Any:
    """Return an ``ExecuteFn`` that routes Decision → BacktestExchange calls.

    The production composition uses ``PositionManager`` to coordinate
    DB persistence + exchange calls; here we skip DB persistence and
    talk to the exchange directly. Pyramiding is rejected up front
    (matches ``PyramidViolationError`` behaviour in prod).
    """
    from omnitrade.domain.value_objects import Leverage, Percentage, Symbol

    async def execute(decision: Decision) -> list[Trade]:
        action = decision.action
        if action == "hold":
            return []
        if decision.symbol is None:
            return []
        sym = Symbol(value=decision.symbol)
        try:
            if action == "open":
                if decision.side is None or decision.size is None:
                    return []
                existing = await exchange.fetch_positions()
                if any(p.symbol == decision.symbol for p in existing):
                    logger.info(
                        "backtest_engine.pyramid_violation",
                        symbol=decision.symbol,
                    )
                    return []
                lev = Leverage(value=int(decision.leverage) if decision.leverage else 1)
                trade = await exchange.place_order(
                    symbol=sym,
                    side=decision.side,
                    size=decision.size,
                    leverage=lev,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                )
                return [trade]
            if action == "close":
                trade = await exchange.close_position(
                    position_id=decision.symbol,
                    percentage=Percentage(value=100.0),
                )
                return [trade]
            if action == "partial_close":
                pct = decision.close_percentage
                if pct is None:
                    return []
                trade = await exchange.close_position(
                    position_id=decision.symbol,
                    percentage=Percentage(value=float(pct)),
                )
                return [trade]
        except Exception as exc:
            logger.warning(
                "backtest_engine.execute_failed",
                action=action,
                symbol=decision.symbol,
                error=str(exc),
            )
        return []

    return execute


async def _passthrough_risk(
    decision: Decision, _positions: list[Position]
) -> Decision:
    return decision


async def _noop_reflect(_decision: Decision, _trades: list[Trade]) -> None:
    return None


# ── BacktestEngine ──────────────────────────────────────────────────── #


class BacktestEngine:
    """End-to-end engine wiring OHLCV + exchange + LLM into ``run_cycle``."""

    def __init__(
        self,
        *,
        exchange: BacktestExchange,
        clock: BacktestClock,
        data_source: HistoricalOHLCV,
        llm: LLMClient,
        settings: Settings,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
        cycle_bars: int = 1,
    ) -> None:
        """
        Args:
            cycle_bars: Run one trading cycle every N primary-timeframe
                bars. Default 1 = every bar. For 4h bars over 1 month
                that is 180 cycles — set to higher values if the LLM
                budget matters.
        """
        self._exchange = exchange
        self._clock = clock
        self._data_source = data_source
        self._llm = llm
        self._settings = settings
        self._symbols = list(symbols)
        self._timeframe = timeframe
        self._start = start.replace(tzinfo=UTC) if start.tzinfo is None else start
        self._end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
        self._cycle_bars = max(1, cycle_bars)

        try:
            self._strategy = StrategyName(settings.trading_strategy)
        except ValueError:
            self._strategy = StrategyName.AI_AUTONOMOUS

    # ── think_fn builder ──────────────────────────────────────────── #

    def _build_think_fn(self) -> Any:
        tool_schemas = _build_tool_schemas()
        tc_policy = _tool_choice_for_strategy(self._strategy)
        # Shared registry — backtest doesn't register tool handlers on
        # it (our strategy is autopilot/dual-signal, which never drives
        # sub-agent calls). A fresh registry per build_think_graph call
        # keeps the graph stateless across cycles.

        async def think_fn(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
            positions = list(market.positions)
            market_block = await _build_backtest_market_block(
                self._exchange, self._symbols
            )
            recent_trades_block = _render_recent_trades_block(
                self._decisions_so_far, market.timestamp
            )
            messages = _render_think_messages(
                strategy=self._strategy,
                market=market,
                news=news,
                positions=positions,
                settings=self._settings,
                iteration=len(self._decisions_so_far),
                minutes_elapsed=0,
                market_data_block=market_block,
                recent_trades_block=recent_trades_block,
            )
            graph = build_think_graph(
                self._llm,
                ToolRegistry(),
                model=self._settings.llm_model_name,
                tools=tool_schemas,
                tool_choice=tc_policy,
            )
            return await invoke_think(graph, messages)

        return think_fn

    # ── observe ──────────────────────────────────────────────────── #

    def _build_observe_fn(self) -> Any:
        async def observe() -> MarketSnapshot:
            tickers_raw = await self._exchange.fetch_tickers(self._symbols)
            tickers = {
                sym: Decimal(str(info["last"]))
                for sym, info in tickers_raw.items()
                if info.get("last") is not None
            }
            positions = await self._exchange.fetch_positions()
            account = await self._exchange.fetch_balance()
            return MarketSnapshot(
                timestamp=self._clock.now(),
                symbols=self._symbols,
                tickers=tickers,
                positions=list(positions),
                account=account,
            )

        return observe

    # ── run ───────────────────────────────────────────────────────── #

    async def run(self) -> BacktestResult:
        """Pre-fetch OHLCV, iterate cycle timestamps, return result."""
        self._decisions_so_far: list[tuple[datetime, Decision]] = []

        start_ms = int(self._start.timestamp() * 1000)
        end_ms = int(self._end.timestamp() * 1000)

        primary_step_ms = timeframe_to_ms(self._timeframe)
        # Warm-up needed for 15m snapshot = ~210 candles of 15m data
        # plus headroom for 1h/4h EMA20. Pull a conservative 7-day
        # warm-up window ahead of the start so indicators converge.
        warmup_ms = 7 * 24 * 60 * 60 * 1000

        # Pre-fetch 15m/1h/4h for every symbol across the full window.
        prefetch_timeframes = ["15m", "1h", "4h"]
        # Also make sure the primary timeframe is in the list.
        if self._timeframe not in prefetch_timeframes:
            prefetch_timeframes.append(self._timeframe)

        for sym in self._symbols:
            for tf in prefetch_timeframes:
                candles = await self._data_source.load(
                    sym,
                    tf,
                    start_ms - warmup_ms,
                    end_ms,
                )
                self._exchange.set_history(sym, tf, candles)
                logger.info(
                    "backtest_engine.prefetched",
                    symbol=sym,
                    tf=tf,
                    rows=len(candles),
                )

        # Compute cycle timestamps — stride over primary timeframe bars
        # in [start_ms, end_ms], every ``cycle_bars`` stride.
        cycle_ts_list: list[int] = []
        ts = start_ms
        # Snap ts to the nearest primary-bar boundary >= start_ms.
        # Assume historical rows land on clean boundaries already.
        while ts <= end_ms:
            cycle_ts_list.append(ts)
            ts += primary_step_ms * self._cycle_bars

        if not cycle_ts_list:
            return BacktestResult(
                symbols=self._symbols,
                timeframe=self._timeframe,
                start=self._start,
                end=self._end,
                strategy=str(self._strategy),
                initial_balance=self._exchange.total_equity,
            )

        # Build observe + execute + think once (they're bar-invariant).
        observe = self._build_observe_fn()
        think_fn = self._build_think_fn()
        execute_fn = _build_execute_fn(self._exchange)

        equity_curve: list[tuple[datetime, Decimal]] = []

        for cycle_idx, cycle_ts_ms in enumerate(cycle_ts_list):
            bars_this_cycle: dict[str, list[float]] = {}
            for sym in self._symbols:
                history = self._exchange._history.get((sym, self._timeframe), [])
                # Latest bar with ts <= cycle_ts_ms
                matching = [r for r in history if int(r[0]) <= cycle_ts_ms]
                if not matching:
                    continue
                bars_this_cycle[sym] = matching[-1]
            if not bars_this_cycle:
                logger.warning(
                    "backtest_engine.no_bar",
                    cycle_ts_ms=cycle_ts_ms,
                )
                continue

            self._exchange.set_current_bars(bars_this_cycle)
            self._clock.set_now(datetime.fromtimestamp(cycle_ts_ms / 1000.0, tz=UTC))

            try:
                outcome: LoopOutcome = await run_cycle(
                    exchange_observe=observe,
                    news_gather=_empty_news,
                    think_fn=think_fn,
                    risk_check=_passthrough_risk,
                    execute_fn=execute_fn,
                    reflect_fn=_noop_reflect,
                    cassette_mode=True,  # never touch WS inside backtest
                )
            except Exception as exc:
                logger.warning(
                    "backtest_engine.cycle_failed",
                    cycle_idx=cycle_idx,
                    cycle_ts_ms=cycle_ts_ms,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                # Record the equity point even on failure so the curve
                # doesn't have gaps.
                equity_curve.append((self._clock.now(), self._exchange.total_equity))
                continue

            self._decisions_so_far.append((self._clock.now(), outcome.decision))
            equity_curve.append((self._clock.now(), self._exchange.total_equity))

        # Assemble result
        metrics = compute_metrics(equity_curve, self._exchange.trades)
        return BacktestResult(
            symbols=self._symbols,
            timeframe=self._timeframe,
            start=self._start,
            end=self._end,
            strategy=str(self._strategy),
            initial_balance=self._exchange._initial_balance,
            equity_curve=equity_curve,
            decisions=list(self._decisions_so_far),
            trades=self._exchange.trades,
            metrics=metrics,
        )


# ── markdown renderer (E3) ─────────────────────────────────────────── #


def _ascii_equity_plot(
    equity_curve: list[tuple[datetime, Decimal]],
    *,
    width: int = 60,
    height: int = 12,
) -> str:
    """Render a simple ASCII plot of the equity curve.

    Subsamples to ``width`` points, scales y to ``height`` rows, plots
    with ``*`` marks. Axis is rudimentary on purpose — the markdown
    report also includes a sampled (ts, eq) table for exact values.
    """
    if not equity_curve:
        return "(no equity data)"
    values = [float(eq) for _ts, eq in equity_curve]
    n = len(values)
    if n == 0:
        return "(no equity data)"

    # Subsample to `width` points
    if n > width:
        step = n / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)

    y_min = min(sampled)
    y_max = max(sampled)
    y_range = y_max - y_min or 1.0

    grid: list[list[str]] = [[" "] * len(sampled) for _ in range(height)]
    for x, v in enumerate(sampled):
        y_norm = (v - y_min) / y_range
        y = height - 1 - int(y_norm * (height - 1))
        y = max(0, min(height - 1, y))
        grid[y][x] = "*"

    rows = ["".join(r) for r in grid]
    top = f"{y_max:>10.2f} |" + rows[0]
    bot = f"{y_min:>10.2f} |" + rows[-1]
    mid = [f"{'':>10} |{r}" for r in rows[1:-1]]
    return "\n".join([top, *mid, bot])


def _sample_equity_rows(
    equity_curve: list[tuple[datetime, Decimal]], n: int = 20
) -> list[tuple[datetime, Decimal]]:
    if not equity_curve:
        return []
    if len(equity_curve) <= n:
        return list(equity_curve)
    step = len(equity_curve) / n
    return [equity_curve[min(len(equity_curve) - 1, int(i * step))] for i in range(n)]


def render_markdown(result: BacktestResult) -> str:
    """Produce the full human-readable backtest report (Phase E3)."""
    m = result.metrics
    syms = ", ".join(result.symbols)
    start_iso = result.start.strftime("%Y-%m-%d")
    end_iso = result.end.strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# Backtest Report — {syms} {start_iso} to {end_iso}")
    lines.append("")
    lines.append(f"Strategy: `{result.strategy}`  |  Timeframe: `{result.timeframe}`  |  "
                 f"Initial Balance: `{result.initial_balance} USDT`")
    lines.append("")

    # Summary metrics
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Initial Equity | {m.get('initial_equity', 0.0):.2f} USDT |")
    lines.append(f"| Final Equity | {m.get('final_equity', 0.0):.2f} USDT |")
    lines.append(f"| Total Return | {m.get('total_return_pct', 0.0):+.2f}% |")
    lines.append(f"| Sharpe (annualised) | {m.get('sharpe_ratio_annualised', 0.0):.2f} |")
    lines.append(f"| Max Drawdown | {m.get('max_drawdown_pct', 0.0):.2f}% |")
    lines.append(f"| Win Rate | {m.get('win_rate', 0.0) * 100:.1f}% |")
    lines.append(f"| Trade Count | {m.get('trade_count', 0)} |")
    lines.append(f"| Avg Win | {m.get('avg_win', 0.0):+.2f} USDT |")
    lines.append(f"| Avg Loss | {m.get('avg_loss', 0.0):+.2f} USDT |")
    lines.append(f"| Profit Factor | {m.get('profit_factor', 0.0):.2f} |")
    lines.append("")

    # Equity plot
    lines.append("## Equity Curve")
    lines.append("")
    lines.append("```")
    lines.append(_ascii_equity_plot(result.equity_curve))
    lines.append("```")
    lines.append("")
    sampled = _sample_equity_rows(result.equity_curve, n=20)
    lines.append("Sampled points:")
    lines.append("")
    lines.append("| Time | Equity |")
    lines.append("|---|---|")
    for ts, eq in sampled:
        lines.append(f"| {ts.strftime('%Y-%m-%d %H:%M')} | {float(eq):.2f} |")
    lines.append("")

    # Decisions
    lines.append(f"## Decisions ({len(result.decisions)} total)")
    lines.append("")
    lines.append("| Time | Action | Symbol | Side | Conf | Reason (brief) |")
    lines.append("|---|---|---|---|---|---|")
    for ts, d in result.decisions:
        conf = (
            f"{d.structured_confidence:.2f}"
            if d.structured_confidence is not None
            else (f"{float(d.confidence):.2f}" if d.confidence is not None else "—")
        )
        brief = (d.market_context or d.reasoning or "").strip().replace("\n", " ")
        if len(brief) > 80:
            brief = brief[:77] + "..."
        lines.append(
            f"| {ts.strftime('%Y-%m-%d %H:%M')} | {d.action} | {d.symbol or '—'} | "
            f"{d.side or '—'} | {conf} | {brief} |"
        )
    lines.append("")

    # Trades
    lines.append(f"## Trades ({len(result.trades)} total)")
    lines.append("")
    lines.append("| Time | Symbol | Side | Type | Price | Size | PnL | Fee |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for t in result.trades:
        pnl_cell = f"{float(t.pnl):+.2f}" if t.pnl is not None else "—"
        fee_cell = f"{float(t.fee):.4f}" if t.fee is not None else "—"
        lines.append(
            f"| {t.timestamp.strftime('%Y-%m-%d %H:%M')} | {t.symbol} | "
            f"{t.side} | {t.type} | {float(t.price):.2f} | {float(t.quantity)} | "
            f"{pnl_cell} | {fee_cell} |"
        )
    lines.append("")
    return "\n".join(lines)


# Small helper kept near the engine so it's easy to add a polling loop
# check without spawning extra tasks if we ever need time budgeting.
def _sleep_noop(_seconds: float) -> Any:
    async def _co() -> None:
        await asyncio.sleep(0)

    return _co()


_unused = timedelta  # keep import silent under strict ruff


__all__ = ["BacktestEngine", "BacktestResult", "iso_to_ms", "render_markdown"]
