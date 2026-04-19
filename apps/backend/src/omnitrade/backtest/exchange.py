"""BacktestExchange — in-memory ``ExchangeClient`` implementation.

Fills orders at the current-bar close price (no slippage, no spread);
applies a flat taker fee and updates cash + positions in-memory.
Suitable as an ``ExchangeClient``-compatible drop-in for the
production composition layer.

Contract vs. protocol
---------------------
Only the subset of ``ExchangeClient`` methods actually exercised by
the trading loop's ``observe_market`` + ``execute`` + think_fn path
has real behavior. The rest (``fetch_funding_rate``,
``fetch_order_book``, ``fetch_open_interest``, ``fetch_open_orders``,
``fetch_order``) return conservative defaults (``0`` / empty / ``None``)
so the protocol is honoured without failing the type checker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.backtest.data_source import HistoricalOHLCV, timeframe_to_ms
from omnitrade.domain.entities import AccountSnapshot, Order, Position, Trade
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol

logger = structlog.get_logger(__name__)


_DEFAULT_FEE_RATE: Decimal = Decimal("0.0005")


class BacktestExchange:
    """Simulated exchange advanced bar-by-bar by the engine.

    The engine calls ``set_current_bars({symbol: [ts, o, h, l, c, v]})``
    before each cycle. Inside the cycle:
        * ``fetch_tickers`` / ``fetch_ticker`` returns the current-bar
          close.
        * ``fetch_positions`` returns open positions with
          ``current_price`` / ``unrealized_pnl`` already marked to the
          latest close.
        * ``fetch_balance`` returns the cash + mark-to-market equity.
        * ``place_order`` fills at the current-bar close, deducts fee
          from cash, creates a new ``Position``.
        * ``close_position`` fully closes at current close, realises
          PnL into cash.

    Leverage in this model scales position *notional* exposure but not
    cash commitment — for simplicity we treat the trader as writing
    margin off cash equal to ``price * size / leverage`` on open (pure
    bookkeeping, not a margin-call check). Phase E1 intentionally
    skips liquidation modelling; the LLM's ``stop_loss`` field in a
    Decision is what the cycle's structured reasoning enforces.
    """

    def __init__(
        self,
        *,
        initial_balance_usdt: Decimal,
        fee_rate: Decimal | None = None,
        data_source: HistoricalOHLCV | None = None,
    ) -> None:
        self._cash: Decimal = initial_balance_usdt
        self._initial_balance: Decimal = initial_balance_usdt
        self._fee_rate: Decimal = fee_rate if fee_rate is not None else _DEFAULT_FEE_RATE
        self._data_source = data_source
        # symbol -> current bar: [ts_ms, o, h, l, c, v]
        self._current_bars: dict[str, list[float]] = {}
        self._positions: dict[str, Position] = {}
        self._trades: list[Trade] = []
        self._now: datetime = datetime(2026, 1, 1, tzinfo=UTC)
        # Cumulative realised pnl (closed trades) since inception — used
        # as the ``realized_pnl`` field of the account snapshot.
        self._realized_pnl: Decimal = Decimal(0)
        # Per-symbol warm-up history pre-fetched by the engine so
        # ``fetch_ohlcv`` can serve it without re-hitting Binance.
        self._history: dict[tuple[str, str], list[list[float]]] = {}
        # Per-cycle cap on the slice returned by ``fetch_ohlcv`` —
        # updated when the engine advances the clock.
        self._cycle_ts_ms: int | None = None

    # ── engine-facing helpers ───────────────────────────────────────── #

    def set_history(
        self, symbol: str, timeframe: str, candles: list[list[float]]
    ) -> None:
        """Pre-load warm-up + forward candles for a symbol/TF.

        Called by the engine during ``BacktestEngine.run`` setup — it
        pre-fetches the full ``[start, end]`` window from the data
        source and hands it over so per-cycle ``fetch_ohlcv`` calls
        become pure in-memory slices.
        """
        self._history[(symbol, timeframe)] = [list(c) for c in candles]

    def set_current_bars(self, bars: dict[str, list[float]]) -> None:
        """Update the live-bar cache and mark-to-market open positions."""
        self._current_bars = {k: list(v) for k, v in bars.items()}
        # Advance the ``cycle_ts_ms`` guard to the latest bar ts.
        max_ts: int | None = None
        for _sym, bar in self._current_bars.items():
            ts = int(bar[0])
            max_ts = ts if max_ts is None else max(max_ts, ts)
        if max_ts is not None:
            self._cycle_ts_ms = max_ts
            self._now = datetime.fromtimestamp(max_ts / 1000.0, tz=UTC)
        # Mark-to-market open positions
        for sym, pos in list(self._positions.items()):
            if sym in self._current_bars:
                close = Decimal(str(self._current_bars[sym][4]))
                side_mult = Decimal(1) if pos.side == "long" else Decimal(-1)
                upnl = (close - pos.entry_price) * pos.quantity * side_mult
                self._positions[sym] = pos.model_copy(
                    update={"current_price": close, "unrealized_pnl": upnl}
                )

    # ── equity / introspection ─────────────────────────────────────── #

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def trades(self) -> list[Trade]:
        return list(self._trades)

    @property
    def total_equity(self) -> Decimal:
        upnl_sum = sum(
            (p.unrealized_pnl for p in self._positions.values()), start=Decimal(0)
        )
        return self._cash + upnl_sum

    # ── ExchangeClient protocol ────────────────────────────────────── #

    async def fetch_balance(self) -> AccountSnapshot:
        total = self.total_equity
        upnl_sum = sum(
            (p.unrealized_pnl for p in self._positions.values()), start=Decimal(0)
        )
        return_pct = Decimal(0)
        if self._initial_balance > Decimal(0):
            return_pct = (total - self._initial_balance) / self._initial_balance * Decimal(100)
        return AccountSnapshot(
            timestamp=self._now,
            total_value=total,
            available_cash=self._cash,
            unrealized_pnl=upnl_sum,
            realized_pnl=self._realized_pnl,
            return_percent=return_pct,
        )

    async def fetch_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def fetch_tickers(
        self, symbols: list[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        tickers: dict[str, dict[str, Any]] = {}
        keys = list(self._current_bars.keys()) if symbols is None else symbols
        for sym in keys:
            bar = self._current_bars.get(sym)
            if not bar:
                continue
            tickers[sym] = {"symbol": sym, "last": float(bar[4])}
        return tickers

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]:
        key = str(symbol)
        bar = self._current_bars.get(key)
        if not bar:
            return {"symbol": key, "last": 0.0}
        return {"symbol": key, "last": float(bar[4])}

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        """Return the last ``limit`` bars up-to-and-including the current bar."""
        key = (str(symbol), timeframe)
        history = self._history.get(key)
        if history is None:
            # Defensive fallback: if no warm-up was pre-loaded the
            # engine forgot to call ``set_history`` — best-effort live
            # fetch so tests that don't pre-fetch still get data.
            if self._data_source is None:
                return []
            step_ms = timeframe_to_ms(timeframe)
            end_ts = self._cycle_ts_ms or int(self._now.timestamp() * 1000)
            start_ts = end_ts - step_ms * (limit - 1)
            history = await self._data_source.load(str(symbol), timeframe, start_ts, end_ts)
            self._history[key] = history

        if self._cycle_ts_ms is None:
            candidates = history
        else:
            # Slice to rows whose ts <= cycle_ts_ms — "no look-ahead".
            candidates = [row for row in history if int(row[0]) <= self._cycle_ts_ms]
        if limit <= 0:
            return []
        return candidates[-limit:]

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade:
        key = str(symbol)
        bar = self._current_bars.get(key)
        if not bar:
            raise ValueError(
                f"BacktestExchange.place_order: no current bar for {key!r} "
                "(did the engine call set_current_bars?)"
            )
        price = Decimal(str(bar[4]))
        notional = price * size
        fee = notional * self._fee_rate
        # Deduct fee from cash (margin is "virtual" here — we track
        # realised pnl on close).
        self._cash -= fee
        order_id = f"bt-{key}-{int(bar[0])}"
        lev_int = int(leverage) if isinstance(leverage, Leverage) else int(leverage)
        trade = Trade(
            order_id=order_id,
            symbol=key,
            side=side,
            type="open",
            price=price,
            quantity=size,
            leverage=lev_int,
            fee=fee,
            timestamp=self._now,
            status="filled",
        )
        self._trades.append(trade)
        # Create or replace the position (backtest does not support
        # pyramiding — engine-level gating matches production).
        self._positions[key] = Position(
            symbol=key,
            quantity=size,
            entry_price=price,
            current_price=price,
            liquidation_price=Decimal(0),
            unrealized_pnl=Decimal(0),
            leverage=lev_int,
            side=side,
            stop_loss=stop_loss,
            profit_target=take_profit,
            entry_order_id=order_id,
            opened_at=self._now,
        )
        logger.info(
            "backtest_exchange.place_order",
            symbol=key,
            side=side,
            price=str(price),
            size=str(size),
            fee=str(fee),
        )
        return trade

    async def close_position(
        self,
        position_id: str,
        percentage: Percentage,
    ) -> Trade:
        """Close (partially or fully) the position keyed by ``position_id``.

        The Gate adapter treats ``position_id`` as the internal symbol
        (``BTC_USDT``) — we follow the same convention.
        """
        key = position_id
        pos = self._positions.get(key)
        if pos is None:
            raise ValueError(f"BacktestExchange.close_position: no position for {key!r}")
        bar = self._current_bars.get(key)
        if not bar:
            raise ValueError(
                f"BacktestExchange.close_position: no current bar for {key!r}"
            )
        fraction = Decimal(str(percentage.as_fraction()))
        close_size = pos.quantity * fraction
        price = Decimal(str(bar[4]))
        side_mult = Decimal(1) if pos.side == "long" else Decimal(-1)
        pnl = (price - pos.entry_price) * close_size * side_mult
        fee = price * close_size * self._fee_rate
        self._cash += pnl - fee
        self._realized_pnl += pnl - fee
        order_id = f"bt-close-{key}-{int(bar[0])}"
        trade = Trade(
            order_id=order_id,
            symbol=key,
            side=pos.side,
            type="close",
            price=price,
            quantity=close_size,
            leverage=pos.leverage,
            pnl=pnl,
            fee=fee,
            timestamp=self._now,
            status="filled",
        )
        self._trades.append(trade)
        remaining = pos.quantity - close_size
        if remaining <= Decimal(0):
            del self._positions[key]
        else:
            # Keep the same entry price; downscale quantity.
            self._positions[key] = pos.model_copy(
                update={
                    "quantity": remaining,
                    "current_price": price,
                    "unrealized_pnl": (price - pos.entry_price) * remaining * side_mult,
                }
            )
        logger.info(
            "backtest_exchange.close_position",
            symbol=key,
            pct=str(percentage.value),
            price=str(price),
            pnl=str(pnl),
        )
        return trade

    # ── no-op / conservative defaults ──────────────────────────────── #

    async def fetch_funding_rate(self, symbol: Symbol) -> Decimal:
        return Decimal(0)

    async def fetch_order_book(
        self, symbol: Symbol, depth: int = 20
    ) -> dict[str, Any]:
        key = str(symbol)
        bar = self._current_bars.get(key)
        last = float(bar[4]) if bar else 0.0
        return {
            "symbol": key,
            "bids": [[last, 0.0]],
            "asks": [[last, 0.0]],
            "timestamp": int(self._now.timestamp() * 1000),
        }

    async def fetch_open_interest(self, symbol: Symbol) -> Decimal:
        return Decimal(0)

    async def fetch_open_orders(
        self, symbol: Symbol | None = None
    ) -> list[Order]:
        return []

    async def fetch_order(
        self, order_id: str, symbol: Symbol
    ) -> Order | None:
        return None

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        return True


__all__ = ["BacktestExchange"]
