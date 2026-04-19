"""Unit tests for trade_execution tools.

The **Phase-0 #4 gap closure** is verified here: both close_position_tool
and partial_close_tool MUST go through PositionRepository.apply_three_way_state
(single atomic UPDATE). Tests assert the method is called with exactly the
expected kwargs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.tools.trade_execution import (
    build_close_position_tool,
    build_hold_tool,
    build_open_position_tool,
    build_partial_close_tool,
)
from omnitrade.domain.entities import Position, Trade
from omnitrade.domain.value_objects import Leverage, Percentage, Symbol


class _StubExchange:
    def __init__(self) -> None:
        self.place_order_calls: list[dict[str, Any]] = []
        self.close_position_calls: list[dict[str, Any]] = []

    async def place_order(
        self,
        symbol: Symbol,
        side: str,
        size: Decimal,
        leverage: Leverage,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Trade:
        self.place_order_calls.append(
            dict(
                symbol=str(symbol),
                side=side,
                size=size,
                leverage=leverage.value,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        )
        return Trade(
            order_id="ord-1",
            symbol=str(symbol),
            side=side,
            type="open",
            price=Decimal("30000"),
            quantity=size,
            leverage=leverage.value,
            fee=Decimal("0.15"),
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            status="closed",
        )

    async def close_position(self, position_id: str, percentage: Percentage) -> Trade:
        self.close_position_calls.append(dict(position_id=position_id, percentage=percentage.value))
        return Trade(
            order_id="ord-2",
            symbol=position_id,
            side="long",
            type="close",
            price=Decimal("31000"),
            quantity=Decimal("0.1"),
            leverage=5,
            pnl=Decimal("100"),
            fee=Decimal("0.16"),
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            status="closed",
        )


class _StubSession:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def close(self) -> None:
        self.closed = True


class _StubRepository:
    def __init__(self, position: Position | None) -> None:
        self._position = position
        self.apply_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    async def get_by_symbol(self, session: Any, symbol: str) -> Position | None:
        self.get_calls.append(symbol)
        return self._position

    async def apply_three_way_state(
        self,
        session: Any,
        position_id: int,
        *,
        partial_close_pct: Decimal,
        stop_loss: Decimal | None,
        peak_pnl: Decimal,
    ) -> None:
        self.apply_calls.append(
            dict(
                position_id=position_id,
                partial_close_pct=partial_close_pct,
                stop_loss=stop_loss,
                peak_pnl=peak_pnl,
            )
        )


def _make_reason_dict() -> dict:
    """Minimal valid StructuredReason payload for test invocations (PR-B2 Phase C)."""
    return {
        "market_context": "a" * 100,
        "gates_passed": ["EMA alignment gate: EMA20 > EMA50 confirms uptrend"],
        "invalidation_condition": "Daily close below 40000 USDT invalidates bias.",
        "plan": None,
        "confidence": 0.7,
        "justification": "b" * 200,
        "output_language": "en",
    }


def _make_position() -> Position:
    return Position(
        id=99,
        symbol="BTC_USDT",
        quantity=Decimal("0.2"),
        entry_price=Decimal("30000"),
        current_price=Decimal("31000"),
        liquidation_price=Decimal("25000"),
        unrealized_pnl=Decimal("200"),
        leverage=5,
        side="long",
        entry_order_id="entry-1",
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        trailing_peak_pnl_pct=Decimal("7.5"),
        cumulative_close_pct=Decimal("30"),
    )


@pytest.mark.asyncio
async def test_open_position_tool_places_order_and_returns_trade() -> None:
    exchange = _StubExchange()
    tool = build_open_position_tool(exchange)  # type: ignore[arg-type]
    result = await tool.ainvoke(
        dict(
            symbol="BTC_USDT",
            side="long",
            size=Decimal("0.1"),
            leverage=5,
            stop_loss=Decimal("29000"),
            take_profit=Decimal("32000"),
            reason=_make_reason_dict(),
        )
    )

    assert result["order_id"] == "ord-1"
    assert result["type"] == "open"
    assert result["price"] == "30000"
    assert len(exchange.place_order_calls) == 1
    call = exchange.place_order_calls[0]
    assert call["symbol"] == "BTC_USDT"
    assert call["leverage"] == 5
    assert call["size"] == Decimal("0.1")


@pytest.mark.asyncio
async def test_close_position_tool_calls_apply_three_way_state() -> None:
    """PHASE-0 #4 GATE — close must route through apply_three_way_state."""
    exchange = _StubExchange()
    repo = _StubRepository(_make_position())
    session = _StubSession()

    async def session_factory() -> Any:
        return session

    reason = _make_reason_dict()
    tool = build_close_position_tool(exchange, repo, session_factory)  # type: ignore[arg-type]
    result = await tool.ainvoke(dict(symbol="BTC_USDT", reason=reason))

    # exchange was told to close 100%
    assert exchange.close_position_calls == [dict(position_id="BTC_USDT", percentage=100.0)]
    # repository.apply_three_way_state was hit exactly once with full-close state
    assert len(repo.apply_calls) == 1
    call = repo.apply_calls[0]
    assert call["position_id"] == 99
    assert call["partial_close_pct"] == Decimal(100)
    assert call["stop_loss"] is None
    assert call["peak_pnl"] == Decimal("7.5")
    # session must be committed + closed
    assert session.committed
    assert session.closed
    # close_reason propagated as dict (PR-B2 Phase C: StructuredReason.model_dump())
    assert isinstance(result["close_reason"], dict)
    assert result["close_reason"]["confidence"] == reason["confidence"]


@pytest.mark.asyncio
async def test_partial_close_tool_calls_apply_three_way_state() -> None:
    """PHASE-0 #4 GATE — partial close must route through apply_three_way_state."""
    exchange = _StubExchange()
    repo = _StubRepository(_make_position())
    session = _StubSession()

    async def session_factory() -> Any:
        return session

    tool = build_partial_close_tool(exchange, repo, session_factory)  # type: ignore[arg-type]
    await tool.ainvoke(
        dict(
            symbol="BTC_USDT",
            percentage=Decimal("25"),
            new_stop_loss=Decimal("2.0"),
            reason=_make_reason_dict(),
        )
    )

    assert exchange.close_position_calls == [dict(position_id="BTC_USDT", percentage=25.0)]
    assert len(repo.apply_calls) == 1
    call = repo.apply_calls[0]
    # cumulative = 30 + 25 = 55
    assert call["partial_close_pct"] == Decimal("55")
    assert call["stop_loss"] == Decimal("2.0")
    assert call["peak_pnl"] == Decimal("7.5")
    assert session.committed
    assert session.closed


@pytest.mark.asyncio
async def test_partial_close_cumulative_capped_at_100() -> None:
    """Cumulative partial_close_pct must saturate at 100."""
    pos = _make_position().model_copy(update={"cumulative_close_pct": Decimal("80")})
    exchange = _StubExchange()
    repo = _StubRepository(pos)
    session = _StubSession()

    async def session_factory() -> Any:
        return session

    tool = build_partial_close_tool(exchange, repo, session_factory)  # type: ignore[arg-type]
    await tool.ainvoke(dict(symbol="BTC_USDT", percentage=Decimal("50"), reason=_make_reason_dict()))

    assert repo.apply_calls[0]["partial_close_pct"] == Decimal(100)


@pytest.mark.asyncio
async def test_close_tool_noop_when_position_missing() -> None:
    """If no position row exists we still return the exchange trade but skip UPDATE."""
    exchange = _StubExchange()
    repo = _StubRepository(position=None)
    session = _StubSession()

    async def session_factory() -> Any:
        return session

    tool = build_close_position_tool(exchange, repo, session_factory)  # type: ignore[arg-type]
    result = await tool.ainvoke(dict(symbol="BTC_USDT", reason=_make_reason_dict()))

    assert result["type"] == "close"
    # apply_three_way_state must NOT be called when no row exists
    assert repo.apply_calls == []
    # but session still gets closed
    assert session.closed


def test_hold_tool_returns_hold_action_with_structured_reason() -> None:
    """PR-B2 Phase C: build_hold_tool emits action=hold + reason dict."""
    tool = build_hold_tool()
    reason = _make_reason_dict()
    result = tool.invoke(dict(reason=reason))

    assert result["action"] == "hold"
    assert isinstance(result["reason"], dict)
    assert result["reason"]["confidence"] == reason["confidence"]
    assert result["reason"]["market_context"] == reason["market_context"]


def test_hold_tool_name_is_hold_tool() -> None:
    """PR-B2 Phase C: tool name must be 'hold_tool' for parser routing."""
    tool = build_hold_tool()
    assert tool.name == "hold_tool"
