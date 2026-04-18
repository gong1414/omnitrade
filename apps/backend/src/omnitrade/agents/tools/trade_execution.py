"""Trade-execution tools — open / close / partial-close a position.

``close_position_tool`` and ``partial_close_tool`` MUST delegate to
``PositionRepository.apply_three_way_state`` so the atomic three-way
UPDATE invariant (see ``domain/services/three_way_state.py``) is preserved
on every agent-initiated close.

Each builder returns a ``StructuredTool`` wired with:
  * an ``ExchangeClient`` for the actual market-side call,
  * a ``PositionRepository`` so the atomic state UPDATE lands in one SQL,
  * an async session factory so each tool call gets its own transaction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import Trade
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.services.three_way_state import apply_three_way_state
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]
"""Returns an open ``AsyncSession`` — caller is responsible for commit/close."""


# ---------------------------------------------------------------------------
# Pydantic input schemas (these drive the tool JSON schema the LLM sees).
# ---------------------------------------------------------------------------


class OpenPositionArgs(BaseModel):
    """Arguments for opening a new futures position."""

    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")
    side: str = Field(description="'long' or 'short'.")
    size: Decimal = Field(description="Position size in contracts.")
    leverage: int = Field(ge=1, le=125, description="Leverage multiplier [1,125].")
    stop_loss: Decimal | None = Field(default=None, description="Stop-loss price.")
    take_profit: Decimal | None = Field(default=None, description="Take-profit price.")


class ClosePositionArgs(BaseModel):
    """Arguments for fully closing an open position."""

    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")
    reason: str = Field(
        default="ai_decision",
        description="One of: stop_loss | trailing_stop | ai_decision.",
    )


class PartialCloseArgs(BaseModel):
    """Arguments for partially closing an open position."""

    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")
    percentage: Decimal = Field(
        gt=Decimal(0),
        le=Decimal(100),
        description="Percentage of the position to close (0 < pct <= 100).",
    )
    new_stop_loss: Decimal | None = Field(
        default=None,
        description="New stop-loss (profit-protection floor). None clears it.",
    )


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# open_position
# ---------------------------------------------------------------------------


def build_open_position_tool(
    exchange: ExchangeClient,
) -> StructuredTool:
    """LangChain tool that opens a new position.

    The tool delegates to ``ExchangeClient.place_order``. No repository
    write here — persistence happens in the outer execute_trades step
    (trading_loop) so the ``positions`` row is created alongside the
    ``trades`` row under one session.
    """

    async def _open_position(
        symbol: str,
        side: str,
        size: Decimal,
        leverage: int,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> dict[str, Any]:
        with_context(logger).info(
            "tool.open_position",
            symbol=symbol,
            side=side,
            size=str(size),
            leverage=leverage,
        )
        trade = await exchange.place_order(
            symbol=Symbol(value=symbol),
            side=side,
            size=size,
            leverage=Leverage(value=leverage),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        return _trade_to_dict(trade)

    return StructuredTool.from_function(
        coroutine=_open_position,
        name="open_position",
        description=(
            "Open a new leveraged futures position. Returns the executed "
            "Trade with price / fee / status. Use `side='long'` to buy, "
            "'short' to sell-short. Stop-loss and take-profit are optional."
        ),
        args_schema=OpenPositionArgs,
    )


# ---------------------------------------------------------------------------
# close_position (full)
# ---------------------------------------------------------------------------


def build_close_position_tool(
    exchange: ExchangeClient,
    repository: PositionRepository,
    session_factory: SessionFactory,
) -> StructuredTool:
    """LangChain tool that fully closes a position.

    Calls ``PositionRepository.apply_three_way_state`` with 100% closed
    — **Phase-0 #4 closure** ensuring the three state-contract fields
    (cumulative_close_pct, stop_loss, trailing_peak_pnl_pct) land in one
    atomic SQL UPDATE (no SELECT-then-UPDATE race).
    """

    async def _close_position(symbol: str, reason: str = "ai_decision") -> dict[str, Any]:
        with_context(logger).info("tool.close_position", symbol=symbol, reason=reason)
        trade = await exchange.close_position(
            position_id=symbol,
            percentage=Percentage(value=100.0),
        )

        session = await session_factory()
        try:
            current = await repository.get_by_symbol(session, symbol)
            if current is None or current.id is None:
                with_context(logger).warning(
                    "tool.close_position.no_row",
                    symbol=symbol,
                )
            else:
                # Three-way state atomic UPDATE — Phase-0 #4 gap closure.
                _ = apply_three_way_state(
                    current,
                    new_cumulative_close_pct=Decimal(100),
                    new_stop_loss=None,
                    new_trailing_peak=current.trailing_peak_pnl_pct,
                )
                await repository.apply_three_way_state(
                    session,
                    current.id,
                    partial_close_pct=Decimal(100),
                    stop_loss=None,
                    peak_pnl=current.trailing_peak_pnl_pct,
                )
                await session.commit()
        finally:
            await session.close()
        return {**_trade_to_dict(trade), "close_reason": reason}

    return StructuredTool.from_function(
        coroutine=_close_position,
        name="close_position",
        description=(
            "Fully close an open position (100%). Emits a single atomic "
            "UPDATE over (cumulative_close_pct, stop_loss, trailing_peak_pnl_pct) "
            "via PositionRepository.apply_three_way_state."
        ),
        args_schema=ClosePositionArgs,
    )


# ---------------------------------------------------------------------------
# partial_close
# ---------------------------------------------------------------------------


def build_partial_close_tool(
    exchange: ExchangeClient,
    repository: PositionRepository,
    session_factory: SessionFactory,
) -> StructuredTool:
    """LangChain tool that partially closes a position.

    Calls ``PositionRepository.apply_three_way_state`` — **Phase-0 #4
    gap closure**. The new cumulative percentage closed is
    min(100, current + requested).
    """

    async def _partial_close(
        symbol: str,
        percentage: Decimal,
        new_stop_loss: Decimal | None = None,
    ) -> dict[str, Any]:
        with_context(logger).info(
            "tool.partial_close",
            symbol=symbol,
            percentage=str(percentage),
        )
        trade = await exchange.close_position(
            position_id=symbol,
            percentage=Percentage(value=float(percentage)),
        )

        session = await session_factory()
        try:
            current = await repository.get_by_symbol(session, symbol)
            if current is None or current.id is None:
                with_context(logger).warning("tool.partial_close.no_row", symbol=symbol)
            else:
                new_cumulative = min(Decimal(100), current.cumulative_close_pct + percentage)
                # Three-way state atomic UPDATE — Phase-0 #4 gap closure.
                await repository.apply_three_way_state(
                    session,
                    current.id,
                    partial_close_pct=new_cumulative,
                    stop_loss=new_stop_loss,
                    peak_pnl=current.trailing_peak_pnl_pct,
                )
                await session.commit()
        finally:
            await session.close()
        return {
            **_trade_to_dict(trade),
            "close_percentage": str(percentage),
        }

    return StructuredTool.from_function(
        coroutine=_partial_close,
        name="partial_close",
        description=(
            "Partially close an open position (pct in (0,100]). Emits a "
            "single atomic UPDATE over the three-way state contract fields "
            "via PositionRepository.apply_three_way_state."
        ),
        args_schema=PartialCloseArgs,
    )


# ---------------------------------------------------------------------------
# Phase 8.4 — cancel_order
# ---------------------------------------------------------------------------


class CancelOrderArgs(BaseModel):
    order_id: str = Field(description="Exchange-assigned order id to cancel.")
    symbol: str = Field(description="Trading pair for the order, e.g. 'BTC_USDT'.")


def build_cancel_order_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _cancel_order(order_id: str, symbol: str) -> dict[str, Any]:
        with_context(logger).info("tool.cancel_order", order_id=order_id, symbol=symbol)
        ok = await exchange.cancel_order(order_id, Symbol(value=symbol))
        return {"order_id": order_id, "symbol": symbol, "cancelled": bool(ok)}

    return StructuredTool.from_function(
        coroutine=_cancel_order,
        name="cancelOrder",
        description=(
            "Cancel a live exchange order by id + symbol. Returns "
            "{cancelled: true} on success; raises on ccxt failure."
        ),
        args_schema=CancelOrderArgs,
    )


__all__ = [
    "CancelOrderArgs",
    "ClosePositionArgs",
    "OpenPositionArgs",
    "PartialCloseArgs",
    "SessionFactory",
    "build_cancel_order_tool",
    "build_close_position_tool",
    "build_open_position_tool",
    "build_partial_close_tool",
]
