"""Smoke tests for Phase-8.4 tool builders (8 new tools)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.tools.account_management import (
    build_check_order_status_tool,
    build_open_orders_tool,
    build_sync_positions_tool,
)
from omnitrade.agents.tools.market_data import (
    build_funding_rate_tool,
    build_open_interest_tool,
    build_order_book_tool,
)
from omnitrade.agents.tools.risk import build_calculate_risk_tool
from omnitrade.agents.tools.trade_execution import build_cancel_order_tool
from omnitrade.domain.entities import Order, Position
from omnitrade.domain.value_objects import Symbol


class _StubExchange:
    def __init__(self) -> None:
        self.fetch_funding_rate_called_with: Symbol | None = None
        self.fetch_order_book_called_with: tuple[Symbol, int] | None = None
        self.fetch_open_interest_called_with: Symbol | None = None
        self.fetch_open_orders_called_with: Symbol | None = None
        self.fetch_order_called_with: tuple[str, Symbol] | None = None
        self.cancel_order_called_with: tuple[str, Symbol] | None = None

    async def fetch_funding_rate(self, symbol: Symbol) -> Decimal:
        self.fetch_funding_rate_called_with = symbol
        return Decimal("0.0001")

    async def fetch_order_book(self, symbol: Symbol, depth: int = 20) -> dict[str, Any]:
        self.fetch_order_book_called_with = (symbol, depth)
        return {"symbol": str(symbol), "bids": [[1.0, 2.0]], "asks": [[1.1, 2.1]], "timestamp": 0}

    async def fetch_open_interest(self, symbol: Symbol) -> Decimal:
        self.fetch_open_interest_called_with = symbol
        return Decimal("999")

    async def fetch_open_orders(self, symbol: Symbol | None = None) -> list[Order]:
        self.fetch_open_orders_called_with = symbol
        return [
            Order(
                id="o-1",
                symbol=Symbol(value="BTC_USDT"),
                side="long",
                status="open",
                price=Decimal("67000"),
                size=Decimal("1"),
                remaining=Decimal("1"),
                timestamp=datetime.now(tz=UTC),
            )
        ]

    async def fetch_order(self, order_id: str, symbol: Symbol) -> Order | None:
        self.fetch_order_called_with = (order_id, symbol)
        if order_id == "missing":
            return None
        return Order(
            id=order_id,
            symbol=symbol,
            side="long",
            status="open",
            price=Decimal("67000"),
            size=Decimal("1"),
            remaining=Decimal("0.5"),
            timestamp=datetime.now(tz=UTC),
        )

    async def cancel_order(self, order_id: str, symbol: Symbol) -> bool:
        self.cancel_order_called_with = (order_id, symbol)
        return True

    async def fetch_positions(self) -> list[Position]:
        return [
            Position(
                id=1,
                symbol="BTC_USDT",
                quantity=Decimal("1"),
                entry_price=Decimal("67000"),
                current_price=Decimal("68000"),
                liquidation_price=Decimal("60000"),
                unrealized_pnl=Decimal("1000"),
                leverage=10,
                side="long",
                entry_order_id="o-entry",
                opened_at=datetime.now(tz=UTC),
            ),
            Position(
                id=2,
                symbol="ETH_USDT",
                quantity=Decimal("5"),
                entry_price=Decimal("3000"),
                current_price=Decimal("3100"),
                liquidation_price=Decimal("2500"),
                unrealized_pnl=Decimal("500"),
                leverage=5,
                side="long",
                entry_order_id="o-entry-2",
                opened_at=datetime.now(tz=UTC),
            ),
        ]


class _StubPositionRepo:
    def __init__(self, local: list[Position]) -> None:
        self._local = local

    async def list_all(self, session: Any) -> list[Position]:
        return self._local


class _StubSession:
    closed = False

    async def close(self) -> None:
        self.closed = True


# ── market data tools ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_funding_rate_tool_returns_decimal_string() -> None:
    exchange = _StubExchange()
    tool = build_funding_rate_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "fundingRate"
    result = await tool.ainvoke({"symbol": "BTC_USDT"})
    assert result == {"symbol": "BTC_USDT", "funding_rate": "0.0001"}
    assert exchange.fetch_funding_rate_called_with == Symbol(value="BTC_USDT")


@pytest.mark.asyncio
async def test_order_book_tool_with_depth() -> None:
    exchange = _StubExchange()
    tool = build_order_book_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "orderBook"
    result = await tool.ainvoke({"symbol": "ETH_USDT", "depth": 10})
    assert result["symbol"] == "ETH_USDT"
    assert exchange.fetch_order_book_called_with == (Symbol(value="ETH_USDT"), 10)


@pytest.mark.asyncio
async def test_order_book_tool_depth_cap_enforced() -> None:
    tool = build_order_book_tool(_StubExchange())  # type: ignore[arg-type]
    # Pydantic arg-schema caps depth at 50.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        await tool.ainvoke({"symbol": "BTC_USDT", "depth": 200})


@pytest.mark.asyncio
async def test_open_interest_tool() -> None:
    exchange = _StubExchange()
    tool = build_open_interest_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "openInterest"
    result = await tool.ainvoke({"symbol": "BTC_USDT"})
    assert result == {"symbol": "BTC_USDT", "open_interest": "999"}


# ── account management tools ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_orders_tool_all_symbols() -> None:
    exchange = _StubExchange()
    tool = build_open_orders_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "openOrders"
    result = await tool.ainvoke({"symbol": None})
    assert result["count"] == 1
    assert result["orders"][0]["id"] == "o-1"
    assert exchange.fetch_open_orders_called_with is None


@pytest.mark.asyncio
async def test_check_order_status_tool_found() -> None:
    exchange = _StubExchange()
    tool = build_check_order_status_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "checkOrderStatus"
    result = await tool.ainvoke({"order_id": "o-42", "symbol": "BTC_USDT"})
    assert result["found"] is True
    assert result["id"] == "o-42"


@pytest.mark.asyncio
async def test_check_order_status_tool_missing() -> None:
    tool = build_check_order_status_tool(_StubExchange())  # type: ignore[arg-type]
    result = await tool.ainvoke({"order_id": "missing", "symbol": "BTC_USDT"})
    assert result == {"found": False, "order_id": "missing"}


@pytest.mark.asyncio
async def test_sync_positions_tool_is_read_only() -> None:
    exchange = _StubExchange()
    # Local DB has SOL position that exchange does not; missing BTC that
    # exchange has; and matching ETH with mismatched size.
    local = [
        Position(
            id=10,
            symbol="SOL_USDT",
            quantity=Decimal("100"),
            entry_price=Decimal("100"),
            current_price=Decimal("100"),
            liquidation_price=Decimal("80"),
            unrealized_pnl=Decimal("0"),
            leverage=2,
            side="long",
            entry_order_id="o-s",
            opened_at=datetime.now(tz=UTC),
        ),
        Position(
            id=11,
            symbol="ETH_USDT",
            quantity=Decimal("7"),  # mismatch vs exchange's 5
            entry_price=Decimal("3000"),
            current_price=Decimal("3100"),
            liquidation_price=Decimal("2500"),
            unrealized_pnl=Decimal("700"),
            leverage=5,
            side="long",
            entry_order_id="o-e",
            opened_at=datetime.now(tz=UTC),
        ),
    ]
    session = _StubSession()

    async def _open_session() -> _StubSession:
        return session

    repo = _StubPositionRepo(local)
    tool = build_sync_positions_tool(exchange, repo, _open_session)  # type: ignore[arg-type]
    assert tool.name == "syncPositions"

    result = await tool.ainvoke({})
    assert result["exchange_count"] == 2
    assert result["local_count"] == 2
    assert result["only_on_exchange"] == ["BTC_USDT"]
    assert result["only_in_local"] == ["SOL_USDT"]
    assert result["size_mismatch"] == [
        {"symbol": "ETH_USDT", "exchange": "5", "local": "7"}
    ]
    assert "READ-ONLY" in result["note"]
    assert session.closed is True


# ── trade execution ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_order_tool() -> None:
    exchange = _StubExchange()
    tool = build_cancel_order_tool(exchange)  # type: ignore[arg-type]
    assert tool.name == "cancelOrder"
    result = await tool.ainvoke({"order_id": "o-9", "symbol": "BTC_USDT"})
    assert result == {"order_id": "o-9", "symbol": "BTC_USDT", "cancelled": True}


# ── risk ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calculate_risk_tool_returns_band_and_budgets() -> None:
    tool = build_calculate_risk_tool()
    assert tool.name == "calculateRisk"
    result = await tool.ainvoke(
        {
            "strategy": "arena-steward",
            "max_leverage": 25,
            "account_equity": Decimal("1000"),
            "confidence": Decimal("1.0"),
        }
    )
    # arena-steward: (max(ceil(0.3*25), 3), max(ceil(0.6*25), 8)) = (8, 15)
    assert result["leverage_band"] == {"min": 8, "max": 15}
    # confidence=1 → suggested = max_lev = 15
    assert result["suggested_leverage"] == 15
    # max_loss = 1000 * 0.02 = 20
    assert result["max_loss_usdt"] == "20.000"
    assert result["risk_fraction"] == "0.020"


@pytest.mark.asyncio
async def test_calculate_risk_tool_invalid_strategy() -> None:
    tool = build_calculate_risk_tool()
    result = await tool.ainvoke(
        {
            "strategy": "nonexistent",
            "max_leverage": 25,
            "account_equity": Decimal("1000"),
            "confidence": Decimal("0.5"),
        }
    )
    assert "error" in result
    assert "valid" in result


@pytest.mark.asyncio
async def test_calculate_risk_tool_confidence_interpolation() -> None:
    tool = build_calculate_risk_tool()
    result = await tool.ainvoke(
        {
            "strategy": "arena-steward",
            "max_leverage": 25,
            "account_equity": Decimal("1000"),
            "confidence": Decimal("0.0"),
        }
    )
    # confidence=0 → suggested = min_lev
    assert result["suggested_leverage"] == 8
    assert result["max_loss_usdt"] == "0.000"
