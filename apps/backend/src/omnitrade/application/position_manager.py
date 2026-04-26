"""PositionManager — open / close / partial_close application service.

All close paths delegate to ``PositionRepository.apply_three_way_state`` so
the three-way state contract (``cumulative_close_pct``, ``stop_loss``,
``trailing_peak_pnl_pct``) always lands in a single atomic UPDATE — see
``domain.services.three_way_state`` and the Phase-0 #4 closure in
``agents.tools.trade_execution``.

Emits ``position_update`` events on every mutation so the WS stream and
dashboard react in real time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.events import EVENT_POSITION_UPDATE, EventBus
from omnitrade.domain.entities import Position, Trade
from omnitrade.domain.errors import PyramidViolationError
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


def _position_to_dict(pos: Position) -> dict[str, Any]:
    return {
        "id": pos.id,
        "symbol": pos.symbol,
        "side": pos.side,
        "quantity": str(pos.quantity),
        "entry_price": str(pos.entry_price),
        "current_price": str(pos.current_price),
        "leverage": pos.leverage,
        "unrealized_pnl": str(pos.unrealized_pnl),
        "stop_loss": str(pos.stop_loss) if pos.stop_loss is not None else None,
        "trailing_peak_pnl_pct": str(pos.trailing_peak_pnl_pct),
        "cumulative_close_pct": str(pos.cumulative_close_pct),
    }


def _trade_to_dict(trade: Trade) -> dict[str, Any]:
    return {
        "order_id": trade.order_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "type": trade.type,
        "price": str(trade.price),
        "quantity": str(trade.quantity),
        "leverage": trade.leverage,
        "pnl": str(trade.pnl) if trade.pnl is not None else None,
        "fee": str(trade.fee) if trade.fee is not None else None,
        "status": trade.status,
    }


class PositionManager:
    """Application-level façade over ``PositionRepository`` + ``ExchangeClient``."""

    def __init__(
        self,
        *,
        exchange: ExchangeClient,
        position_repo: PositionRepository,
        trade_repo: TradeRepository,
        session_factory: SessionFactory,
        event_bus: EventBus,
    ) -> None:
        self._exchange = exchange
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._session_factory = session_factory
        self._event_bus = event_bus

    async def open_position(
        self,
        *,
        symbol: str,
        side: str,
        size: Decimal,
        leverage: int,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        confidence: Decimal | None = None,
    ) -> Trade:
        """Open a new position via the exchange and persist it.

        Returns the settlement ``Trade`` (order-id, fill price, fee).

        Raises:
            PyramidViolationError: when an OPEN position already exists for
                ``symbol``. Alpha Arena's no-pyramid rule forbids adding to
                existing positions or re-entering a held coin; the caller
                (``composition._build_execute_fn``) catches this gracefully
                so the cycle's StructuredReason still records.
        """
        # Alpha Arena no-pyramid rule: refuse to open a second position in
        # a symbol that already has a row in the ``positions`` table with
        # non-zero quantity. Cross-check with the exchange to avoid stale
        # DB rows blocking new positions (the earlier close may have
        # succeeded on the exchange but failed to update the DB).
        session = await self._session_factory()
        try:
            existing = await self._position_repo.get_by_symbol(session, symbol)
        finally:
            await session.close()
        if existing is not None and existing.quantity > Decimal(0):
            # Verify the position actually exists on the exchange.
            try:
                exchange_positions = await self._exchange.fetch_positions()
                on_exchange = any(
                    p.symbol == symbol and p.quantity > Decimal(0) for p in exchange_positions
                )
                if not on_exchange:
                    with_context(logger).warning(
                        "position_manager.stale_db_position",
                        symbol=symbol,
                        db_qty=str(existing.quantity),
                    )
                    session = await self._session_factory()
                    try:
                        await self._position_repo.delete(session, existing.id)
                        await session.commit()
                    finally:
                        await session.close()
                else:
                    raise PyramidViolationError(
                        f"Already holding {symbol} (side={existing.side}, "
                        f"qty={existing.quantity}). No pyramid: cannot open new "
                        f"position in same symbol."
                    )
            except PyramidViolationError:
                raise
            except Exception as exc:
                with_context(logger).warning(
                    "position_manager.pyramid_check_exchange_failed",
                    symbol=symbol,
                    error=str(exc),
                )
                raise PyramidViolationError(
                    f"Already holding {symbol} (side={existing.side}, "
                    f"qty={existing.quantity}). No pyramid: cannot open new "
                    f"position in same symbol."
                ) from exc

        with_context(logger).info(
            "position_manager.open_position",
            symbol=symbol,
            side=side,
            size=str(size),
            leverage=leverage,
        )
        trade = await self._exchange.place_order(
            symbol=Symbol(value=symbol),
            side=side,
            size=size,
            leverage=Leverage(value=leverage),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        session = await self._session_factory()
        try:
            await self._trade_repo.create(session, trade)
            new_pos = Position(
                symbol=symbol,
                quantity=size,
                entry_price=trade.price,
                current_price=trade.price,
                liquidation_price=Decimal(0),
                unrealized_pnl=Decimal(0),
                leverage=leverage,
                side=side,
                stop_loss=stop_loss,
                entry_order_id=trade.order_id,
                opened_at=datetime.now(tz=UTC),
                confidence=confidence,
            )
            persisted = await self._position_repo.create(session, new_pos)
            await session.commit()
        finally:
            await session.close()

        await self._event_bus.publish(
            EVENT_POSITION_UPDATE,
            {"action": "open", "position": _position_to_dict(persisted)},
        )
        return trade

    async def close_position(self, *, symbol: str, reason: str = "ai_decision") -> Trade:
        """Fully close the position for ``symbol`` (100%).

        Emits exactly one atomic UPDATE over the three-way state contract
        fields via ``PositionRepository.apply_three_way_state``.
        """
        with_context(logger).info(
            "position_manager.close_position",
            symbol=symbol,
            reason=reason,
        )
        trade = await self._exchange.close_position(
            position_id=symbol,
            percentage=Percentage(value=100.0),
        )

        session = await self._session_factory()
        try:
            current = await self._position_repo.get_by_symbol(session, symbol)
            await self._trade_repo.create(session, trade)
            if current is not None and current.id is not None:
                await self._position_repo.apply_three_way_state(
                    session,
                    current.id,
                    partial_close_pct=Decimal(100),
                    stop_loss=None,
                    peak_pnl=current.trailing_peak_pnl_pct,
                )
            await session.commit()
        finally:
            await session.close()

        await self._event_bus.publish(
            EVENT_POSITION_UPDATE,
            {
                "action": "close",
                "symbol": symbol,
                "reason": reason,
                "trade": _trade_to_dict(trade),
            },
        )
        return trade

    async def partial_close(
        self,
        *,
        symbol: str,
        percentage: Decimal,
        new_stop_loss: Decimal | None = None,
        reason: str = "ai_decision",
    ) -> Trade:
        """Partially close the position for ``symbol``.

        Cumulative partial close saturates at 100%. Updates all three
        state-contract fields in one atomic SQL UPDATE.
        """
        if not (Decimal(0) < percentage <= Decimal(100)):
            raise ValueError(f"partial_close percentage must be in (0, 100], got {percentage}")
        with_context(logger).info(
            "position_manager.partial_close",
            symbol=symbol,
            percentage=str(percentage),
        )
        trade = await self._exchange.close_position(
            position_id=symbol,
            percentage=Percentage(value=float(percentage)),
        )

        session = await self._session_factory()
        try:
            current = await self._position_repo.get_by_symbol(session, symbol)
            await self._trade_repo.create(session, trade)
            if current is not None and current.id is not None:
                new_cumulative = min(Decimal(100), current.cumulative_close_pct + percentage)
                await self._position_repo.apply_three_way_state(
                    session,
                    current.id,
                    partial_close_pct=new_cumulative,
                    stop_loss=new_stop_loss if new_stop_loss is not None else current.stop_loss,
                    peak_pnl=current.trailing_peak_pnl_pct,
                )
            await session.commit()
        finally:
            await session.close()

        await self._event_bus.publish(
            EVENT_POSITION_UPDATE,
            {
                "action": "partial_close",
                "symbol": symbol,
                "percentage": str(percentage),
                "reason": reason,
                "trade": _trade_to_dict(trade),
            },
        )
        return trade


__all__ = ["PositionManager", "SessionFactory"]
