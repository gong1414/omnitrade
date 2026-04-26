"""BacktestEngine — bar-by-bar replay of the Agno trading think_fn.

The engine drives :class:`omnitrade.backtest.exchange.BacktestExchange`
through a historical OHLCV window, calling an injected ``think_fn`` once
per cycle. The think_fn returns a :class:`Decision`; the engine
dispatches it via the in-memory exchange and records the resulting
trades + equity curve.

Design choices
--------------
* The think_fn is a constructor parameter, not a built-in dependency.
  Production code (``omnitrade.backtest.agno_think.build_backtest_think_fn``)
  builds an Agno Agent + DeepSeek-backed think_fn that mirrors the live
  trading path; tests can pass a stub that returns canned ``Decision``
  values without ever touching the LLM.
* The engine never touches the Postgres / FastAPI container — it only
  uses the four collaborator objects (``exchange``, ``clock``,
  ``data_source``, ``think_fn``) plus :class:`Settings` for prompt
  rendering.
* OHLCV is pre-fetched per ``(symbol, timeframe)`` once at startup and
  fed to ``BacktestExchange.set_history`` so per-cycle ``fetch_ohlcv``
  calls are pure in-memory slices (no Binance round-trips inside the
  hot loop).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.data_source import HistoricalOHLCV
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.backtest.metrics import compute_metrics
from omnitrade.config import Settings
from omnitrade.domain.entities import (
    Decision,
    MarketSnapshot,
    NewsItem,
    Trade,
)
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol

logger = structlog.get_logger(__name__)


# ``ThinkFn`` mirrors the production ``omnitrade.application.trading_loop.ThinkFn``
# alias so callers can wire the same shape into either system.
ThinkFn = Callable[[MarketSnapshot, list[NewsItem]], Awaitable[Decision]]


@dataclass
class BacktestResult:
    """Result of a completed backtest run."""

    strategy: str = ""
    symbols: list[str] = field(default_factory=list)
    timeframe: str = ""
    start: datetime | None = None
    end: datetime | None = None
    cycles_run: int = 0
    decisions: list[Decision] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render a self-contained markdown report for the run."""
        start_iso = self.start.isoformat() if self.start else "—"
        end_iso = self.end.isoformat() if self.end else "—"
        symbols_str = ", ".join(self.symbols) or "—"
        m = self.metrics

        lines: list[str] = [
            f"# Backtest report — {self.strategy}",
            "",
            f"- Symbols: `{symbols_str}`",
            f"- Timeframe: `{self.timeframe}`",
            f"- Window: `{start_iso}` → `{end_iso}`",
            f"- Cycles run: **{self.cycles_run}**",
            "",
            "## Metrics",
            "",
            f"- Total return: **{m.get('total_return_pct', 0.0):+.2f}%**",
            f"- Sharpe (annualised): **{m.get('sharpe_ratio_annualised', 0.0):.2f}**",
            f"- Max drawdown: **{m.get('max_drawdown_pct', 0.0):.2f}%**",
            f"- Trade count: **{m.get('trade_count', 0)}**",
            f"- Win rate: **{m.get('win_rate_pct', 0.0):.1f}%**",
        ]

        # Trades table — capped so 1k-cycle runs don't print megabytes.
        if self.trades:
            lines.extend(["", "## Trades (last 25)", ""])
            lines.append("| ts | symbol | side | type | qty | price | pnl |")
            lines.append("|---|---|---|---|---|---|---|")
            for t in self.trades[-25:]:
                pnl = t.pnl if t.pnl is not None else "—"
                lines.append(
                    f"| {t.timestamp.isoformat()} | {t.symbol} | {t.side} | "
                    f"{t.type} | {t.quantity} | {t.price} | {pnl} |"
                )

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


_NEWS_NONE: list[NewsItem] = []
"""Backtests skip the news source — historical news fetching is out of scope.
The think_fn receives an empty list, matching the production fallback path."""


class BacktestEngine:
    """Drive the trading think_fn over a historical window."""

    def __init__(
        self,
        *,
        exchange: BacktestExchange,
        clock: BacktestClock,
        data_source: HistoricalOHLCV,
        think_fn: ThinkFn,
        settings: Settings,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "4h",
        cycle_bars: int = 1,
    ) -> None:
        if cycle_bars < 1:
            raise ValueError(f"cycle_bars must be >= 1, got {cycle_bars}")
        if end <= start:
            raise ValueError(f"end ({end}) must be after start ({start})")
        self._exchange = exchange
        self._clock = clock
        self._data_source = data_source
        self._think_fn = think_fn
        self._settings = settings
        self._symbols = list(symbols)
        self._start = start if start.tzinfo else start.replace(tzinfo=UTC)
        self._end = end if end.tzinfo else end.replace(tzinfo=UTC)
        self._timeframe = timeframe
        self._cycle_bars = cycle_bars

    async def _prefetch_history(self) -> dict[str, list[list[float]]]:
        """Pull ``[start, end]`` candles for every symbol and seed the exchange."""
        start_ms = int(self._start.timestamp() * 1000)
        end_ms = int(self._end.timestamp() * 1000)
        primary: dict[str, list[list[float]]] = {}
        for sym in self._symbols:
            candles = await self._data_source.load(sym, self._timeframe, start_ms, end_ms)
            if not candles:
                raise ValueError(
                    f"BacktestEngine: data source returned no candles for "
                    f"{sym!r} timeframe={self._timeframe} window=[{start_ms},{end_ms}]"
                )
            self._exchange.set_history(sym, self._timeframe, candles)
            primary[sym] = candles

            # Pre-load 1h + 4h higher-TF candles too (used by the prompt
            # rendering helpers when the production composition layer is
            # wired). 4h is the primary; 1h is denser. Fetch best-effort —
            # the engine still runs if a higher TF is unavailable.
            for extra_tf in ("1h", "4h"):
                if extra_tf == self._timeframe:
                    continue
                try:
                    extra_candles = await self._data_source.load(
                        sym, extra_tf, start_ms, end_ms
                    )
                except Exception as exc:  # extra TFs are best-effort
                    logger.warning(
                        "backtest_engine.prefetch_extra_tf_failed",
                        symbol=sym,
                        timeframe=extra_tf,
                        error=str(exc),
                    )
                    continue
                if extra_candles:
                    self._exchange.set_history(sym, extra_tf, extra_candles)
        return primary

    async def _run_cycle(
        self,
        bar_index: int,
        bars_per_symbol: dict[str, list[float]],
    ) -> tuple[Decision, list[Trade]]:
        """Drive a single cycle: observe → think → execute, return outcomes."""
        # Advance the exchange & clock to the latest bar.
        self._exchange.set_current_bars(bars_per_symbol)
        max_ts_ms = max(int(bar[0]) for bar in bars_per_symbol.values())
        bar_dt = datetime.fromtimestamp(max_ts_ms / 1000.0, tz=UTC)
        self._clock.set_now(bar_dt)

        # Build the market snapshot from the exchange (it already knows
        # tickers + positions + balance).
        balance = await self._exchange.fetch_balance()
        positions = await self._exchange.fetch_positions()
        tickers = {
            sym: Decimal(str(bar[4]))  # close
            for sym, bar in bars_per_symbol.items()
        }
        market = MarketSnapshot(
            timestamp=bar_dt,
            symbols=list(self._symbols),
            tickers=tickers,
            positions=list(positions),
            account=balance,
        )

        # Call the injected think_fn — it produces a Decision.
        try:
            decision = await self._think_fn(market, _NEWS_NONE)
        except Exception as exc:
            logger.error(
                "backtest_engine.think_failed",
                cycle=bar_index,
                error=str(exc),
            )
            decision = Decision(
                action="hold",
                reasoning=f"think_fn_failed: {exc!r}",
            )

        # Dispatch the decision via the BacktestExchange.
        executed_trades = await self._dispatch_decision(decision)
        return decision, executed_trades

    async def _dispatch_decision(self, decision: Decision) -> list[Trade]:
        """Apply ``decision`` to ``self._exchange``; return the executed trades.

        Mirrors :func:`omnitrade.application.composition._build_execute_fn`'s
        contract: actions other than ``open`` / ``close`` / ``partial_close``
        return ``[]`` (``hold``); malformed fields are logged + swallowed
        so a single bad LLM cycle can't nuke the whole run.
        """
        action = decision.action
        try:
            if action == "open":
                if decision.symbol is None or decision.side is None:
                    return []
                size = decision.size or self._settings.default_position_size
                leverage = decision.leverage or self._settings.default_leverage
                trade = await self._exchange.place_order(
                    symbol=Symbol(value=decision.symbol),
                    side=decision.side,
                    size=Decimal(str(size)),
                    leverage=Leverage(value=int(leverage)),
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                )
                return [trade]
            if action == "close":
                if decision.symbol is None:
                    return []
                trade = await self._exchange.close_position(
                    position_id=decision.symbol,
                    percentage=Percentage(value=100.0),
                )
                return [trade]
            if action == "partial_close":
                if decision.symbol is None or decision.close_percentage is None:
                    return []
                pct = float(decision.close_percentage)
                trade = await self._exchange.close_position(
                    position_id=decision.symbol,
                    percentage=Percentage(value=pct),
                )
                return [trade]
            return []
        except Exception as exc:
            logger.warning(
                "backtest_engine.execute_failed",
                action=action,
                symbol=decision.symbol,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return []

    async def run(self) -> BacktestResult:
        """Iterate the historical window and replay the trading think_fn.

        Returns a fully-populated :class:`BacktestResult`. The engine
        deliberately does NOT close ``self._exchange`` / ``self._data_source``
        — the CLI owns their lifetime.
        """
        primary_history = await self._prefetch_history()
        # Choose the canonical bar timeline from the first symbol — every
        # other symbol must align (their bar count should match because the
        # data source covers the same window). We zip-shortest to skip
        # mismatched tails.
        canonical = min(primary_history.values(), key=len)
        n_bars = len(canonical)
        if n_bars < self._cycle_bars:
            raise ValueError(
                f"BacktestEngine: only {n_bars} bars in window — need at "
                f"least cycle_bars={self._cycle_bars}"
            )

        decisions: list[Decision] = []
        equity_curve: list[tuple[datetime, Decimal]] = []
        cycles_run = 0

        # Iterate one cycle every `cycle_bars` bars so a 1h timeframe with
        # cycle_bars=4 mimics a 4h cadence without re-fetching candles.
        per_symbol_bars: dict[str, list[list[float]]] = primary_history
        for idx in range(0, n_bars, self._cycle_bars):
            current_bars: dict[str, list[float]] = {}
            for sym in self._symbols:
                series = per_symbol_bars.get(sym)
                if series and idx < len(series):
                    current_bars[sym] = series[idx]
            if not current_bars:
                continue
            decision, _ = await self._run_cycle(idx, current_bars)
            decisions.append(decision)
            cycles_run += 1
            equity_curve.append((self._clock.now(), self._exchange.total_equity))

        metrics = compute_metrics(
            equity_curve=equity_curve,
            trades=self._exchange.trades,
        )
        return BacktestResult(
            strategy=self._settings.trading_strategy,
            symbols=list(self._symbols),
            timeframe=self._timeframe,
            start=self._start,
            end=self._end,
            cycles_run=cycles_run,
            decisions=decisions,
            trades=list(self._exchange.trades),
            equity_curve=equity_curve,
            metrics=metrics,
        )


__all__ = ["BacktestEngine", "BacktestResult", "ThinkFn"]
