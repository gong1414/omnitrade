"""Domain protocols — abstract seams between domain and infrastructure.

All protocols are runtime-checkable via typing.Protocol + @runtime_checkable.
These define the ports; infrastructure adapters implement the adapters.
No infrastructure imports here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from omnitrade.domain.entities import AccountSnapshot, Order, Position, Trade, TradingLesson
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol


@runtime_checkable
class ExchangeClient(Protocol):
    """Abstraction over a futures exchange (Gate.io / OKX)."""

    async def fetch_balance(self) -> AccountSnapshot: ...

    async def fetch_positions(self) -> list[Position]: ...

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade: ...

    async def close_position(
        self,
        position_id: str,
        percentage: Percentage,
    ) -> Trade: ...

    async def fetch_ticker(self, symbol: Symbol) -> dict[str, Any]: ...

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]: ...

    # ── Phase 8.0 port-boundary extensions (stubs; wired in Phase 8.4). ───────── #

    async def fetch_funding_rate(self, symbol: Symbol) -> Decimal: ...

    async def fetch_order_book(
        self,
        symbol: Symbol,
        depth: int = 20,
    ) -> dict[str, Any]: ...

    async def fetch_open_interest(self, symbol: Symbol) -> Decimal: ...

    async def fetch_open_orders(
        self,
        symbol: Symbol | None = None,
    ) -> list[Order]: ...

    async def fetch_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> Order | None: ...

    async def cancel_order(
        self,
        order_id: str,
        symbol: Symbol,
    ) -> bool: ...


@runtime_checkable
class LLMClient(Protocol):
    """Abstraction over a language model provider (LiteLLM / DeepSeek / etc.)."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Abstraction over a vector similarity store (sqlite-vec / Chroma)."""

    async def add(
        self,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> str: ...

    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[TradingLesson, float]]: ...

    async def delete(self, lesson_id: str) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    """Abstraction over an async event bus (in-process or external)."""

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None: ...

    def subscribe(
        self,
        event_name: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None: ...
