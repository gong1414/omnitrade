"""CCXTExchange — ccxt-based adapter implementing ExchangeClient protocol.

Supports Gate.io (gateio) and OKX with testnet/sandbox mode.
Implements all 6 ExchangeClient methods.

Phase-0 finding resolutions:
  #4 — close_position() returns settlement Trade so PositionRepository can
       update cumulative_close_pct atomically.
  #9 — fee rate pulled from ccxt exchange.fees or Settings.exchange_fee_rate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import ccxt.async_support as ccxt_async
import structlog

from omnitrade.domain.entities import AccountSnapshot, Order, Position, Trade
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol
from omnitrade.infrastructure.exchange.contract_mapping import (
    ccxt_to_gate,
    gate_to_ccxt,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

_DEFAULT_FEE_RATE = Decimal("0.0005")  # Phase-0 finding #9 default


class CCXTExchange:
    """ccxt-based ExchangeClient for Gate.io and OKX futures.

    Args:
        exchange_id: "gate" or "okx".
        api_key: Exchange API key.
        api_secret: Exchange API secret.
        testnet: If True, use sandbox/testnet endpoints (default).
        passphrase: OKX API passphrase (required for OKX).
        fee_rate: Override taker fee rate; None = pull from ccxt exchange.fees.
    """

    def __init__(
        self,
        exchange_id: Literal["gate", "okx"],
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
        passphrase: str | None = None,
        fee_rate: Decimal | None = None,
    ) -> None:
        self._exchange_id = exchange_id
        self._fee_rate_override = fee_rate
        self._exchange = self._build_exchange(
            exchange_id, api_key, api_secret, testnet=testnet, passphrase=passphrase
        )

    @staticmethod
    def _build_exchange(
        exchange_id: Literal["gate", "okx"],
        api_key: str,
        api_secret: str,
        *,
        testnet: bool,
        passphrase: str | None,
    ) -> ccxt_async.Exchange:
        config: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "swap"},
        }
        if exchange_id == "gate":
            ex: ccxt_async.Exchange = ccxt_async.gateio(config)
        elif exchange_id == "okx":
            if passphrase:
                config["password"] = passphrase
            ex = ccxt_async.okx(config)
        else:
            raise ValueError(f"Unsupported exchange_id: {exchange_id!r}")

        if testnet:
            ex.set_sandbox_mode(True)

        return ex

    def _to_ccxt_symbol(self, symbol: Symbol) -> str:
        """Convert internal symbol (BTC_USDT) to ccxt unified (BTC/USDT:USDT)."""
        return gate_to_ccxt(str(symbol))

    def _from_ccxt_symbol(self, ccxt_sym: str) -> str:
        """Convert ccxt unified symbol back to internal (Gate) format."""
        return ccxt_to_gate(ccxt_sym)

    def _effective_fee_rate(self) -> Decimal:
        """Return the taker fee rate: override > ccxt exchange.fees > default."""
        if self._fee_rate_override is not None:
            return self._fee_rate_override
        try:
            fees = self._exchange.fees
            taker = fees.get("trading", {}).get("taker")
            if taker is not None:
                return Decimal(str(taker))
        except Exception as exc:
            with_context(logger).debug("ccxt_exchange.fee_rate_fallback", error=str(exc))
        return _DEFAULT_FEE_RATE

    async def fetch_balance(self) -> AccountSnapshot:
        """Fetch account balance and return as AccountSnapshot."""
        with_context(logger).info("ccxt_exchange.fetch_balance", exchange=self._exchange_id)
        raw = await self._exchange.fetch_balance({"type": "swap"})
        total = Decimal(str(raw.get("total", {}).get("USDT", 0)))
        free = Decimal(str(raw.get("free", {}).get("USDT", 0)))
        upnl_raw = raw.get("info", {})
        unrealized_pnl = Decimal("0")
        # Gate.io nests unrealised_pnl differently from OKX; best-effort parse
        if isinstance(upnl_raw, dict):
            for key in ("unrealised_pnl", "unrealized_pnl", "upl"):
                val = upnl_raw.get(key)
                if val is not None:
                    unrealized_pnl = Decimal(str(val))
                    break

        # Gate.io `total` does NOT include unrealized PnL — must add it
        # to get the true account value (same pattern as nof1.ai).
        total_with_upnl = total + unrealized_pnl

        return AccountSnapshot(
            timestamp=datetime.now(tz=UTC),
            total_value=total_with_upnl,
            available_cash=free,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=Decimal("0"),
            return_percent=Decimal("0"),
        )

    async def fetch_positions(self) -> list[Position]:
        """Fetch open positions and return as domain Position list."""
        with_context(logger).info("ccxt_exchange.fetch_positions", exchange=self._exchange_id)
        raw_positions = await self._exchange.fetch_positions()
        positions: list[Position] = []
        for p in raw_positions:
            # `contracts` = open-position size (0 means no position).
            # `contractSize` = per-contract underlying (a constant like 1.0
            # or 0.01) and MUST NOT be used as a fallback — that turned every
            # empty ccxt position slot into a phantom position the LLM saw
            # as real holdings with entry_price=0.
            contracts = p.get("contracts") or 0
            if not contracts:
                continue
            side_raw = (p.get("side") or "long").lower()
            side = "long" if side_raw in ("long", "buy") else "short"
            symbol_ccxt = p.get("symbol", "")
            internal_symbol = self._from_ccxt_symbol(symbol_ccxt)
            entry_price = Decimal(str(p.get("entryPrice") or p.get("entry_price") or 0))
            mark_price = Decimal(str(p.get("markPrice") or p.get("mark_price") or entry_price))
            liq_price = Decimal(str(p.get("liquidationPrice") or p.get("liquidation_price") or 0))
            upnl = Decimal(str(p.get("unrealizedPnl") or p.get("unrealised_pnl") or 0))
            leverage = int(p.get("leverage") or 1)
            positions.append(
                Position(
                    symbol=internal_symbol,
                    quantity=Decimal(str(contracts)),
                    entry_price=entry_price,
                    current_price=mark_price,
                    liquidation_price=liq_price,
                    unrealized_pnl=upnl,
                    leverage=leverage,
                    side=side,
                    entry_order_id=str(p.get("id") or ""),
                    opened_at=datetime.now(tz=UTC),
                )
            )
        return positions

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade:
        """Place a futures order and return a Trade domain entity."""
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        ccxt_side = "buy" if side == "long" else "sell"
        with_context(logger).info(
            "ccxt_exchange.place_order",
            symbol=str(symbol),
            side=side,
            size=str(size),
            leverage=leverage.value,
        )
        # Set leverage before placing order
        try:
            await self._exchange.set_leverage(leverage.value, ccxt_symbol)
        except Exception as exc:
            with_context(logger).warning(
                "ccxt_exchange.set_leverage_failed",
                symbol=str(symbol),
                error=str(exc),
            )

        params: dict[str, Any] = {}
        # Gate.io does not support stopLossPrice + takeProfitPrice on the
        # same order.  Following nof1.ai's approach: open the position with a
        # plain market order and let the code-level monitors (stop_loss,
        # trailing_stop, partial_profit) enforce exit conditions.

        amount = float(size)
        # Round amount to exchange precision and enforce minimums.
        try:
            amount = self._exchange.amount_to_precision(ccxt_symbol, amount)
            amount = float(amount)
        except Exception as exc:
            with_context(logger).warning(
                "ccxt_exchange.amount_precision_fallback",
                symbol=str(symbol),
                amount=str(amount),
                error=str(exc),
            )
        # Gate.io perpetuals require integer contract counts; amount_to_precision
        # may still return <1. Clamp to the market's minimum amount.
        try:
            market = self._exchange.market(ccxt_symbol)
            min_amount = (market.get("limits", {}).get("amount", {}).get("min")) or 0
            if min_amount and amount < float(min_amount):
                with_context(logger).info(
                    "ccxt_exchange.amount_clamped_to_min",
                    symbol=str(symbol),
                    original=str(amount),
                    minimum=str(min_amount),
                )
                amount = float(min_amount)
            # Re-apply precision after clamping (e.g. round to integer).
            amount = float(self._exchange.amount_to_precision(ccxt_symbol, amount))
        except Exception:
            pass

        if amount <= 0:
            raise ValueError(
                f"Order amount rounded to zero for {symbol} "
                f"(requested {size}). Account too small for minimum contract size."
            )

        raw_order = await self._exchange.create_order(
            symbol=ccxt_symbol,
            type="market",
            side=ccxt_side,
            amount=amount,
            params=params,
        )

        fee_rate = self._effective_fee_rate()
        price = Decimal(str(raw_order.get("price") or raw_order.get("average") or 0))
        fee = price * size * fee_rate

        return Trade(
            order_id=str(raw_order.get("id", "")),
            symbol=str(symbol),
            side=side,
            type="open",
            price=price,
            quantity=size,
            leverage=leverage.value,
            fee=fee,
            timestamp=datetime.now(tz=UTC),
            status=raw_order.get("status", "pending"),
        )

    async def close_position(
        self,
        position_id: str,
        percentage: Percentage,
    ) -> Trade:
        """Close a percentage of a position.

        Returns a Trade with the settlement details needed by PositionRepository
        to update cumulative_close_pct atomically (Phase-0 finding #4).

        position_id is the internal Gate symbol (e.g. "BTC_USDT").
        """
        ccxt_symbol = gate_to_ccxt(position_id)
        with_context(logger).info(
            "ccxt_exchange.close_position",
            position_id=position_id,
            percentage=percentage.value,
        )
        # Fetch current position to determine size
        positions = await self._exchange.fetch_positions([ccxt_symbol])
        if not positions:
            raise ValueError(f"No open position found for {position_id!r}")

        pos = positions[0]
        contracts = Decimal(str(pos.get("contracts") or 0))
        close_size = contracts * Decimal(str(percentage.as_fraction()))
        side_raw = (pos.get("side") or "long").lower()
        # To close: if long -> sell; if short -> buy
        close_side = "sell" if side_raw in ("long", "buy") else "buy"

        close_amount = float(close_size)
        try:
            close_amount = self._exchange.amount_to_precision(ccxt_symbol, close_amount)
            close_amount = float(close_amount)
        except Exception:
            pass

        # Gate.io perpetuals require integer-contract amounts. A partial
        # close of a position already at the exchange minimum rounds to 0
        # after ``amount_to_precision`` and the exchange rejects with
        # ``InvalidOrder: must be greater than minimum amount precision of
        # 1``. When that happens, escalate to a full close using the raw
        # ``contracts`` value so the LLM's risk-reduction intent actually
        # lands — the alternative (silent InvalidOrder on every cycle)
        # left positions stuck for hours with no visible trades.
        if close_amount < 1.0 and contracts > Decimal(0):
            escalated = float(contracts)
            try:
                escalated = float(
                    self._exchange.amount_to_precision(ccxt_symbol, escalated)
                )
            except Exception:
                pass
            with_context(logger).warning(
                "ccxt_exchange.partial_close_escalated_to_full",
                position_id=position_id,
                contracts=str(contracts),
                requested_pct=percentage.value,
                original_close_amount=close_amount,
                escalated_close_amount=escalated,
            )
            close_amount = escalated
            close_size = contracts

        raw_order = await self._exchange.create_order(
            symbol=ccxt_symbol,
            type="market",
            side=close_side,
            amount=close_amount,
            params={"reduceOnly": True},
        )

        price = Decimal(str(raw_order.get("price") or raw_order.get("average") or 0))
        fee_rate = self._effective_fee_rate()

        # Unit reconciliation: ``close_size`` is counted in exchange
        # contracts (e.g. 1 contract on Gate BTC_USDT perp = 0.001 BTC)
        # while ``place_order`` stores ``quantity`` in base-asset units.
        # Multiplying raw contract count into fee/pnl inflated those
        # columns by 1/contractSize (roughly 1000×) which made the
        # dashboard show plausible-but-nonsense numbers. Resolve
        # contractSize from the market metadata so we can record both the
        # executed contract count (for audit) and the base-asset amount
        # (for fee/pnl) consistently.
        try:
            market = self._exchange.market(ccxt_symbol)
            contract_size = Decimal(str(market.get("contractSize") or 1))
        except Exception:
            contract_size = Decimal(1)
        base_qty = close_size * contract_size

        fee = price * base_qty * fee_rate
        pnl = Decimal(str(raw_order.get("realizedPnl") or raw_order.get("pnl") or 0))
        entry_price = Decimal(str(pos.get("entryPrice") or 0))
        if pnl == Decimal("0") and price > Decimal("0") and entry_price > Decimal("0"):
            multiplier = Decimal("1") if side_raw in ("long", "buy") else Decimal("-1")
            pnl = (price - entry_price) * base_qty * multiplier

        return Trade(
            order_id=str(raw_order.get("id", "")),
            symbol=position_id,
            side=side_raw if side_raw in ("long", "short") else "long",
            type="close",
            price=price,
            # Store base-asset quantity (BTC) so the trades table reads
            # consistently alongside the open rows.
            quantity=base_qty,
            leverage=int(pos.get("leverage") or 1),
            pnl=pnl,
            fee=fee,
            timestamp=datetime.now(tz=UTC),
            status=raw_order.get("status", "pending"),
        )

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]:
        """Fetch current ticker for a symbol."""
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        with_context(logger).debug("ccxt_exchange.fetch_ticker", symbol=str(symbol))
        result: dict[str, Any] = await self._exchange.fetch_ticker(ccxt_symbol)
        return dict(result)

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        """Fetch OHLCV candles."""
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        with_context(logger).debug(
            "ccxt_exchange.fetch_ohlcv",
            symbol=str(symbol),
            timeframe=timeframe,
            limit=limit,
        )
        raw = await self._exchange.fetch_ohlcv(ccxt_symbol, timeframe=timeframe, limit=limit)
        return [list(candle) for candle in raw]

    # ── Phase 8.4 real implementations (stubs retired). ──────────────────────── #

    async def fetch_funding_rate(self, symbol: Symbol) -> Decimal:
        """Latest funding rate for a perpetual swap contract."""
        with_context(logger).info(
            "ccxt_exchange.fetch_funding_rate",
            exchange=self._exchange_id,
            symbol=str(symbol),
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        raw = await self._exchange.fetch_funding_rate(ccxt_symbol)
        rate = raw.get("fundingRate")
        if rate is None:
            raise ValueError(f"ccxt fetch_funding_rate returned no fundingRate for {symbol}")
        return Decimal(str(rate))

    async def fetch_order_book(
        self,
        symbol: Symbol,
        depth: int = 20,
    ) -> dict[str, Any]:
        """Order-book snapshot: ``{bids: [[price, amount]], asks: [...], timestamp}``."""
        with_context(logger).info(
            "ccxt_exchange.fetch_order_book",
            exchange=self._exchange_id,
            symbol=str(symbol),
            depth=depth,
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        raw = await self._exchange.fetch_order_book(ccxt_symbol, limit=depth)
        return {
            "symbol": str(symbol),
            "bids": [[float(p), float(a)] for p, a in (raw.get("bids") or [])[:depth]],
            "asks": [[float(p), float(a)] for p, a in (raw.get("asks") or [])[:depth]],
            "timestamp": raw.get("timestamp"),
        }

    async def fetch_open_interest(self, symbol: Symbol) -> Decimal:
        """Current open interest for a swap contract (amount units)."""
        with_context(logger).info(
            "ccxt_exchange.fetch_open_interest",
            exchange=self._exchange_id,
            symbol=str(symbol),
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        raw = await self._exchange.fetch_open_interest(ccxt_symbol)
        # Prefer openInterestAmount (contracts); fall back to openInterestValue
        # (quote currency) if the exchange doesn't publish amount.
        amount = raw.get("openInterestAmount")
        if amount is None:
            amount = raw.get("openInterestValue")
        if amount is None:
            raise ValueError(f"ccxt fetch_open_interest returned no OI for {symbol}")
        return Decimal(str(amount))

    async def fetch_open_orders(
        self,
        symbol: Symbol | None = None,
    ) -> list[Order]:
        """List live (open) orders, optionally filtered to a single symbol."""
        with_context(logger).info(
            "ccxt_exchange.fetch_open_orders",
            exchange=self._exchange_id,
            symbol=str(symbol) if symbol else None,
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol) if symbol else None
        raw = await self._exchange.fetch_open_orders(ccxt_symbol)
        return [self._order_from_ccxt(o) for o in raw]

    async def fetch_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> Order | None:
        """Fetch a single order by id, or None if it no longer exists."""
        with_context(logger).info(
            "ccxt_exchange.fetch_order",
            exchange=self._exchange_id,
            order_id=order_id,
            symbol=str(symbol),
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        try:
            raw = await self._exchange.fetch_order(order_id, ccxt_symbol)
        except Exception as exc:  # ccxt raises OrderNotFound / NetworkError
            with_context(logger).warning(
                "ccxt_exchange.fetch_order_failed",
                exchange=self._exchange_id,
                order_id=order_id,
                error=str(exc),
            )
            return None
        if not raw:
            return None
        return self._order_from_ccxt(raw)

    async def cancel_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> bool:
        """Cancel a live order by id; True on success, raises on failure."""
        with_context(logger).info(
            "ccxt_exchange.cancel_order",
            exchange=self._exchange_id,
            order_id=order_id,
            symbol=str(symbol),
        )
        ccxt_symbol = self._to_ccxt_symbol(symbol)
        await self._exchange.cancel_order(order_id, ccxt_symbol)
        return True

    def _order_from_ccxt(self, raw: dict[str, Any]) -> Order:
        """Translate a ccxt unified order dict into a domain ``Order`` entity.

        ccxt side is ``"buy"`` / ``"sell"``; we fold both into the
        domain's ``long`` / ``short`` literal. For derivatives this is a
        best-effort mapping consistent with upstream convention.
        """
        side_raw = str(raw.get("side", "")).lower()
        side: Literal["long", "short"] = "long" if side_raw == "buy" else "short"

        status_raw = str(raw.get("status", "")).lower()
        status: Literal["open", "filled", "cancelled", "partially_filled"]
        if status_raw == "closed":
            status = "filled"
        elif status_raw == "canceled":
            status = "cancelled"
        elif status_raw in {"open", "partially_filled"}:
            status = status_raw  # type: ignore[assignment]
        else:
            status = "open"

        ts_ms = raw.get("timestamp")
        ts = (
            datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=UTC)
            if isinstance(ts_ms, (int, float))
            else datetime.now(tz=UTC)
        )

        ccxt_sym_str = str(raw.get("symbol", ""))
        internal_sym = (
            self._from_ccxt_symbol(ccxt_sym_str)
            if ccxt_sym_str
            else str(raw.get("symbol", ""))
        )

        return Order(
            id=str(raw.get("id", "")),
            symbol=Symbol(value=internal_sym),
            side=side,
            status=status,
            price=Decimal(str(raw.get("price") or 0)),
            size=Decimal(str(raw.get("amount") or 0)),
            remaining=Decimal(str(raw.get("remaining") or 0)),
            timestamp=ts,
        )

    async def close(self) -> None:
        """Close the underlying ccxt exchange connection."""
        await self._exchange.close()
