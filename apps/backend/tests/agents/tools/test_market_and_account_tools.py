"""Unit tests for market-data + account tools (read-only passthroughs)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.tools.account_management import (
    build_account_snapshot_tool,
    build_list_positions_tool,
)
from omnitrade.agents.tools.market_data import (
    build_fetch_ohlcv_tool,
    build_fetch_ticker_tool,
)
from omnitrade.domain.entities import AccountSnapshot, Position
from omnitrade.domain.value_objects import Symbol


class _ReadOnlyExchange:
    async def fetch_balance(self) -> AccountSnapshot:
        return AccountSnapshot(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            total_value=Decimal("1000"),
            available_cash=Decimal("800"),
            unrealized_pnl=Decimal("50"),
            realized_pnl=Decimal("20"),
            return_percent=Decimal("5"),
        )

    async def fetch_positions(self) -> list[Position]:
        return [
            Position(
                id=1,
                symbol="BTC_USDT",
                quantity=Decimal("0.1"),
                entry_price=Decimal("30000"),
                current_price=Decimal("31000"),
                liquidation_price=Decimal("25000"),
                unrealized_pnl=Decimal("100"),
                leverage=5,
                side="long",
                entry_order_id="e-1",
                opened_at=datetime(2026, 1, 1, tzinfo=UTC),
                trailing_peak_pnl_pct=Decimal("4.2"),
                cumulative_close_pct=Decimal("10"),
                stop_loss=Decimal("1.5"),
            )
        ]

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]:
        return {"last": 31000, "bid": 30999, "ask": 31001, "symbol": str(symbol)}

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        return [[1700000000000.0, 30000.0, 31000.0, 29500.0, 30500.0, 123.0]]


@pytest.mark.asyncio
async def test_fetch_ticker_tool() -> None:
    tool = build_fetch_ticker_tool(_ReadOnlyExchange())  # type: ignore[arg-type]
    result = await tool.ainvoke(dict(symbol="BTC_USDT"))
    assert result["last"] == 31000
    assert result["symbol"] == "BTC_USDT"


@pytest.mark.asyncio
async def test_fetch_ohlcv_tool() -> None:
    tool = build_fetch_ohlcv_tool(_ReadOnlyExchange())  # type: ignore[arg-type]
    result = await tool.ainvoke(dict(symbol="BTC_USDT", timeframe="1m", limit=1))
    assert result["timeframe"] == "1m"
    assert len(result["candles"]) == 1


@pytest.mark.asyncio
async def test_account_snapshot_tool() -> None:
    tool = build_account_snapshot_tool(_ReadOnlyExchange())  # type: ignore[arg-type]
    result = await tool.ainvoke({})
    assert result["total_value"] == "1000"
    assert result["available_cash"] == "800"


@pytest.mark.asyncio
async def test_list_positions_tool() -> None:
    tool = build_list_positions_tool(_ReadOnlyExchange())  # type: ignore[arg-type]
    result = await tool.ainvoke({})
    assert result["count"] == 1
    pos = result["positions"][0]
    assert pos["symbol"] == "BTC_USDT"
    assert pos["stop_loss"] == "1.5"
    assert pos["leverage"] == 5
