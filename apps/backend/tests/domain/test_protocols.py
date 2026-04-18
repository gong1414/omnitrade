"""Tests for domain protocols — structural subtyping via isinstance checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import pytest

from omnitrade.domain.entities import AccountSnapshot, Order, Position, Trade, TradingLesson
from omnitrade.domain.protocols import EventBus, ExchangeClient, LLMClient, VectorStore
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _make_position() -> Position:
    return Position(
        symbol="BTCUSDT",
        quantity=Decimal("1"),
        entry_price=Decimal("68000"),
        current_price=Decimal("69000"),
        liquidation_price=Decimal("50000"),
        unrealized_pnl=Decimal("1000"),
        leverage=10,
        side="long",
        entry_order_id="order-001",
        opened_at=_utcnow(),
    )


def _make_trade() -> Trade:
    return Trade(
        order_id="ord-001",
        symbol="BTCUSDT",
        side="long",
        type="open",
        price=Decimal("68000"),
        quantity=Decimal("0.1"),
        leverage=10,
        timestamp=_utcnow(),
    )


def _make_snapshot() -> AccountSnapshot:
    return AccountSnapshot(
        timestamp=_utcnow(),
        total_value=Decimal("10000"),
        available_cash=Decimal("5000"),
        unrealized_pnl=Decimal("500"),
        realized_pnl=Decimal("200"),
        return_percent=Decimal("7.0"),
    )


# ── Fake implementations ──────────────────────────────────────────────────────── #


class FakeExchangeClient:
    async def fetch_balance(self) -> AccountSnapshot:
        return _make_snapshot()

    async def fetch_positions(self) -> list[Position]:
        return [_make_position()]

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade:
        return _make_trade()

    async def close_position(
        self,
        position_id: str,
        percentage: Percentage,
    ) -> Trade:
        return _make_trade()

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]:
        return {"last": "68000"}

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        return [[1.0, 2.0, 3.0, 4.0, 5.0]]

    async def fetch_funding_rate(self, symbol: Symbol) -> Decimal:
        return Decimal("0.0001")

    async def fetch_order_book(
        self,
        symbol: Symbol,
        depth: int = 20,
    ) -> dict[str, Any]:
        return {"bids": [], "asks": []}

    async def fetch_open_interest(self, symbol: Symbol) -> Decimal:
        return Decimal("0")

    async def fetch_open_orders(
        self,
        symbol: Symbol | None = None,
    ) -> list[Order]:
        return []

    async def fetch_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> Order | None:
        return None

    async def cancel_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> bool:
        return True


class FakeLLMClient:
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]:
        return {"content": "hold"}


class FakeVectorStore:
    async def add(
        self,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> str:
        return "lesson-id-001"

    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[TradingLesson, float]]:
        return []

    async def delete(self, lesson_id: str) -> None:
        pass


class FakeEventBus:
    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        pass

    def subscribe(
        self,
        event_name: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        pass


# ── Protocol structural subtyping tests ───────────────────────────────────────── #


class TestExchangeClientProtocol:
    def test_isinstance_check(self) -> None:
        client = FakeExchangeClient()
        assert isinstance(client, ExchangeClient)

    def test_non_conformant_fails(self) -> None:
        class BadClient:
            pass

        assert not isinstance(BadClient(), ExchangeClient)


class TestLLMClientProtocol:
    def test_isinstance_check(self) -> None:
        client = FakeLLMClient()
        assert isinstance(client, LLMClient)

    def test_non_conformant_fails(self) -> None:
        class BadClient:
            pass

        assert not isinstance(BadClient(), LLMClient)


class TestVectorStoreProtocol:
    def test_isinstance_check(self) -> None:
        store = FakeVectorStore()
        assert isinstance(store, VectorStore)

    def test_non_conformant_fails(self) -> None:
        class BadStore:
            pass

        assert not isinstance(BadStore(), VectorStore)


class TestEventBusProtocol:
    def test_isinstance_check(self) -> None:
        bus = FakeEventBus()
        assert isinstance(bus, EventBus)

    def test_non_conformant_fails(self) -> None:
        class BadBus:
            pass

        assert not isinstance(BadBus(), EventBus)


# ── Async smoke tests ─────────────────────────────────────────────────────────── #


@pytest.mark.asyncio
async def test_fake_exchange_client_fetch_balance() -> None:
    client = FakeExchangeClient()
    snap = await client.fetch_balance()
    assert snap.total_value == Decimal("10000")


@pytest.mark.asyncio
async def test_fake_llm_client_complete() -> None:
    client = FakeLLMClient()
    result = await client.complete(messages=[{"role": "user", "content": "test"}], model="gpt-4")
    assert "content" in result


@pytest.mark.asyncio
async def test_fake_vector_store_add() -> None:
    store = FakeVectorStore()
    lid = await store.add("pattern text", [0.1, 0.2], {"symbol": "BTC"})
    assert lid == "lesson-id-001"


@pytest.mark.asyncio
async def test_fake_event_bus_publish() -> None:
    bus = FakeEventBus()
    # Should not raise
    await bus.publish("trade_executed", {"symbol": "BTC"})
