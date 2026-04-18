"""Account-management tools — fetch balance snapshot and current positions.

Wraps ``ExchangeClient.fetch_balance`` / ``fetch_positions``. Read-only;
no state writes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class NoArgs(BaseModel):
    """Tools that take no arguments still need an empty args_schema."""


def build_account_snapshot_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _account_snapshot() -> dict[str, Any]:
        with_context(logger).info("tool.account_snapshot")
        snap = await exchange.fetch_balance()
        return {
            "total_value": str(snap.total_value),
            "available_cash": str(snap.available_cash),
            "unrealized_pnl": str(snap.unrealized_pnl),
            "realized_pnl": str(snap.realized_pnl),
            "return_percent": str(snap.return_percent),
            "timestamp": snap.timestamp.isoformat(),
        }

    return StructuredTool.from_function(
        coroutine=_account_snapshot,
        name="account_snapshot",
        description="Fetch the current account balance snapshot (total / free / uPnL).",
        args_schema=NoArgs,
    )


def build_list_positions_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _list_positions() -> dict[str, Any]:
        with_context(logger).info("tool.list_positions")
        positions = await exchange.fetch_positions()
        return {
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "quantity": str(p.quantity),
                    "entry_price": str(p.entry_price),
                    "current_price": str(p.current_price),
                    "unrealized_pnl": str(p.unrealized_pnl),
                    "leverage": p.leverage,
                    "stop_loss": str(p.stop_loss) if p.stop_loss is not None else None,
                    "cumulative_close_pct": str(p.cumulative_close_pct),
                    "trailing_peak_pnl_pct": str(p.trailing_peak_pnl_pct),
                }
                for p in positions
            ],
            "count": len(positions),
        }

    return StructuredTool.from_function(
        coroutine=_list_positions,
        name="list_positions",
        description="List all currently open positions with size / pnl / leverage.",
        args_schema=NoArgs,
    )


# ---------------------------------------------------------------------------
# Phase 8.4 — open orders / order status / sync positions (read-only)
# ---------------------------------------------------------------------------


class OpenOrdersArgs(BaseModel):
    symbol: str | None = Field(
        default=None,
        description="Optional symbol filter; omit to list all live orders.",
    )


class CheckOrderArgs(BaseModel):
    order_id: str = Field(description="Exchange-assigned order id.")
    symbol: str = Field(description="Trading pair for the order, e.g. 'BTC_USDT'.")


class SyncPositionsArgs(BaseModel):
    """No arguments — tool diffs all open positions against the local DB."""


SessionFactory = Callable[[], Awaitable[AsyncSession]]


def build_open_orders_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _open_orders(symbol: str | None = None) -> dict[str, Any]:
        with_context(logger).debug("tool.open_orders", symbol=symbol)
        sym = Symbol(value=symbol) if symbol else None
        orders = await exchange.fetch_open_orders(sym)
        return {
            "orders": [
                {
                    "id": o.id,
                    "symbol": str(o.symbol),
                    "side": o.side,
                    "status": o.status,
                    "price": str(o.price),
                    "size": str(o.size),
                    "remaining": str(o.remaining),
                    "timestamp": o.timestamp.isoformat(),
                }
                for o in orders
            ],
            "count": len(orders),
        }

    return StructuredTool.from_function(
        coroutine=_open_orders,
        name="openOrders",
        description=(
            "List live (open / partially filled) exchange orders. Pass `symbol` "
            "to filter; omit for all symbols."
        ),
        args_schema=OpenOrdersArgs,
    )


def build_check_order_status_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _check_order(order_id: str, symbol: str) -> dict[str, Any]:
        with_context(logger).debug(
            "tool.check_order_status", order_id=order_id, symbol=symbol
        )
        order = await exchange.fetch_order(order_id, Symbol(value=symbol))
        if order is None:
            return {"found": False, "order_id": order_id}
        return {
            "found": True,
            "id": order.id,
            "symbol": str(order.symbol),
            "side": order.side,
            "status": order.status,
            "price": str(order.price),
            "size": str(order.size),
            "remaining": str(order.remaining),
            "timestamp": order.timestamp.isoformat(),
        }

    return StructuredTool.from_function(
        coroutine=_check_order,
        name="checkOrderStatus",
        description=(
            "Look up a single exchange order by id + symbol. Returns "
            "{found: false} when the exchange no longer has the order."
        ),
        args_schema=CheckOrderArgs,
    )


def build_sync_positions_tool(
    exchange: ExchangeClient,
    repository: PositionRepository,
    session_factory: SessionFactory,
) -> StructuredTool:
    """READ-ONLY position reconciliation for LLM inspection.

    This tool is intentionally non-mutating when invoked from the agent:
    it diffs exchange state vs the local ``positions`` table and returns
    the delta. Actual reconciliation (DB writes) happens in the
    ``scripts/sync_positions.py`` CLI (Phase 8.6) with `--apply --yes-really`.
    """

    async def _sync_positions() -> dict[str, Any]:
        with_context(logger).info("tool.sync_positions.diff_only")
        exchange_positions = await exchange.fetch_positions()

        session = await session_factory()
        try:
            local_positions = await repository.list_all(session)
        finally:
            await session.close()

        exch_by_sym = {p.symbol: p for p in exchange_positions}
        local_by_sym = {p.symbol: p for p in local_positions if p.symbol}

        only_exchange = sorted(set(exch_by_sym) - set(local_by_sym))
        only_local = sorted(set(local_by_sym) - set(exch_by_sym))
        both = sorted(set(exch_by_sym) & set(local_by_sym))
        size_mismatch: list[dict[str, Any]] = []
        for sym in both:
            e_qty = exch_by_sym[sym].quantity
            l_qty = local_by_sym[sym].quantity
            if e_qty != l_qty:
                size_mismatch.append(
                    {"symbol": sym, "exchange": str(e_qty), "local": str(l_qty)}
                )

        return {
            "exchange_count": len(exchange_positions),
            "local_count": len(local_positions),
            "only_on_exchange": only_exchange,
            "only_in_local": only_local,
            "size_mismatch": size_mismatch,
            "note": "READ-ONLY diff. Run scripts/sync_positions.py for reconciliation.",
        }

    return StructuredTool.from_function(
        coroutine=_sync_positions,
        name="syncPositions",
        description=(
            "READ-ONLY diff of exchange open positions vs the local "
            "`positions` table. Returns symbols only-on-exchange, "
            "only-in-local, and size mismatches. Does NOT write. Use the "
            "`scripts/sync_positions.py` CLI for actual reconciliation."
        ),
        args_schema=SyncPositionsArgs,
    )


__all__ = [
    "CheckOrderArgs",
    "NoArgs",
    "OpenOrdersArgs",
    "SessionFactory",
    "SyncPositionsArgs",
    "build_account_snapshot_tool",
    "build_check_order_status_tool",
    "build_list_positions_tool",
    "build_open_orders_tool",
    "build_sync_positions_tool",
]
