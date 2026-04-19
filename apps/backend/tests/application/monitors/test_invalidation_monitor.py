"""InvalidationMonitor — auto-close OPEN positions when their
LLM-authored ``invalidation_condition`` trips against fresh 15m market.

PR-D Phase D2, task 2. Verifies the 5 contract points:
  * triggered=true  → ``PositionManager.close_position`` fires
  * triggered=false → no close
  * missing invalidation text → skipped, no LLM call
  * LLM raises      → logged, loop continues to next symbol
  * insufficient OHLCV (<50 candles) → skipped before LLM call
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.application.events import EventBus
from omnitrade.application.monitors.invalidation_monitor import InvalidationMonitor
from omnitrade.application.position_manager import PositionManager
from omnitrade.domain.entities import AgentDecision, Position
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.multi_timeframe import (
    MultiTimeframeFetcher,
)
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from tests.application._fakes import (
    FakeExchange,
    build_sqlite_session_factory,
    make_trade,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubLLM:
    """Captures ``complete`` calls and returns scripted content."""

    def __init__(
        self,
        *,
        responses: list[Any] | None = None,
        raise_on_call: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = responses or []
        self._raise = raise_on_call

    async def complete(  # type: ignore[no-untyped-def]
        self,
        messages,
        model,
        temperature=0.7,
        tools=None,
        tool_choice=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        if self._raise is not None:
            raise self._raise
        if not self._responses:
            return {
                "choices": [
                    {"message": {"content": '{"triggered": false, "reason": "default"}'}}
                ]
            }
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class _ShortOhlcvExchange:
    """ExchangeClient stub that returns fewer candles than the snapshot
    minimum — used to exercise the ``insufficient_ohlcv`` branch.
    """

    def __init__(self) -> None:
        self.fetch_ohlcv_calls: list[tuple[str, str, int]] = []

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int,
    ) -> list[list[float]]:
        self.fetch_ohlcv_calls.append((str(symbol), timeframe, limit))
        # 10 candles << 50 minimum in ``snapshot_from_ohlcv``.
        return [
            [float(i * 60_000), 100.0, 101.0, 99.0, 100.0 + i, 10.0] for i in range(10)
        ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _open_position(symbol: str = "BTC_USDT") -> Position:
    return Position(
        symbol=symbol,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        liquidation_price=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        leverage=5,
        side="long",
        entry_order_id=f"ord-{symbol}",
        opened_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


def _decision_with_invalidation(
    *,
    symbol: str,
    invalidation: str | None,
    iteration: int = 1,
    ts: datetime | None = None,
) -> AgentDecision:
    return AgentDecision(
        timestamp=ts or datetime(2026, 4, 18, 12, iteration, tzinfo=UTC),
        iteration=iteration,
        market_analysis="{}",
        decision="open",
        actions_taken=json.dumps([{"symbol": symbol, "side": "long", "order_id": "ord-1"}]),
        account_value=Decimal("1000"),
        positions_count=1,
        market_context="ctx",
        gates_passed=["g1"],
        invalidation_condition=invalidation,
        plan={"entry": 100},
        structured_confidence=0.7,
        output_language="en",
    )


async def _seed(
    open_session,
    *,
    position: Position | None,
    decision: AgentDecision | None,
) -> None:
    session = await open_session()
    try:
        if position is not None:
            await PositionRepository().create(session, position)
        if decision is not None:
            await DecisionRepository().create(session, decision)
        await session.commit()
    finally:
        await session.close()


def _build_monitor(
    *,
    open_session,
    llm: Any,
    exchange: Any,
    multi_tf_fetcher: MultiTimeframeFetcher,
    close_trade=None,
) -> tuple[InvalidationMonitor, FakeExchange]:
    """Wire a monitor with a PositionManager whose close call is tracked."""
    position_exchange = FakeExchange(
        close_trade=close_trade or make_trade(ttype="close", order_id="ord-close"),
    )
    pm = PositionManager(
        exchange=position_exchange,
        position_repo=PositionRepository(),
        trade_repo=TradeRepository(),
        session_factory=open_session,
        event_bus=EventBus(),
    )
    mon = InvalidationMonitor(
        interval_seconds=60,
        llm=llm,
        model="deepseek/deepseek-chat",
        exchange=exchange,
        multi_tf_fetcher=multi_tf_fetcher,
        position_repo=PositionRepository(),
        decision_repo=DecisionRepository(),
        position_manager=pm,
        session_factory=open_session,
    )
    return mon, position_exchange


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidation_triggers_close() -> None:
    """LLM returns triggered=true → PositionManager.close_position fires."""
    _factory, open_session = await build_sqlite_session_factory()
    await _seed(
        open_session,
        position=_open_position("BTC_USDT"),
        decision=_decision_with_invalidation(
            symbol="BTC_USDT",
            invalidation="Close below 90 on 15m",
        ),
    )

    exchange = FakeExchange()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=InMemoryTTLCache(),
    )
    llm = _StubLLM(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"triggered": true, "reason": "15m closed under 90"}'
                        }
                    }
                ]
            }
        ]
    )
    mon, position_exchange = _build_monitor(
        open_session=open_session,
        llm=llm,
        exchange=exchange,
        multi_tf_fetcher=fetcher,
    )

    await mon.tick()

    assert len(position_exchange.close_calls) == 1
    assert position_exchange.close_calls[0]["position_id"] == "BTC_USDT"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_invalidation_no_trigger() -> None:
    """LLM returns triggered=false → no close call."""
    _factory, open_session = await build_sqlite_session_factory()
    await _seed(
        open_session,
        position=_open_position("BTC_USDT"),
        decision=_decision_with_invalidation(
            symbol="BTC_USDT",
            invalidation="Close below 50 on 15m",
        ),
    )

    exchange = FakeExchange()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=InMemoryTTLCache(),
    )
    llm = _StubLLM(
        responses=[
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"triggered": false, "reason": "still above 50"}'
                        }
                    }
                ]
            }
        ]
    )
    mon, position_exchange = _build_monitor(
        open_session=open_session,
        llm=llm,
        exchange=exchange,
        multi_tf_fetcher=fetcher,
    )

    await mon.tick()

    assert position_exchange.close_calls == []
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_empty_invalidation_skipped() -> None:
    """Position with no invalidation text → skip without hitting the LLM."""
    _factory, open_session = await build_sqlite_session_factory()
    await _seed(
        open_session,
        position=_open_position("BTC_USDT"),
        decision=_decision_with_invalidation(
            symbol="BTC_USDT",
            invalidation=None,
        ),
    )

    exchange = FakeExchange()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=InMemoryTTLCache(),
    )
    llm = _StubLLM()
    mon, position_exchange = _build_monitor(
        open_session=open_session,
        llm=llm,
        exchange=exchange,
        multi_tf_fetcher=fetcher,
    )

    await mon.tick()

    assert position_exchange.close_calls == []
    assert llm.calls == []  # LLM must NOT be called when there is no text


@pytest.mark.asyncio
async def test_llm_failure_non_fatal() -> None:
    """LLM raises on first symbol → second symbol still processed."""
    _factory, open_session = await build_sqlite_session_factory()
    # Seed two positions with invalidation text.
    await _seed(
        open_session,
        position=_open_position("BTC_USDT"),
        decision=_decision_with_invalidation(
            symbol="BTC_USDT",
            invalidation="Close below 90",
            iteration=1,
        ),
    )
    await _seed(
        open_session,
        position=_open_position("ETH_USDT"),
        decision=_decision_with_invalidation(
            symbol="ETH_USDT",
            invalidation="Close below 90",
            iteration=2,
        ),
    )

    exchange = FakeExchange()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=InMemoryTTLCache(),
    )
    # First call explodes, second call returns a no-trigger verdict.
    llm = _StubLLM(
        responses=[
            RuntimeError("boom — rate limited"),
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"triggered": false, "reason": "fine"}'
                        }
                    }
                ]
            },
        ]
    )
    mon, position_exchange = _build_monitor(
        open_session=open_session,
        llm=llm,
        exchange=exchange,
        multi_tf_fetcher=fetcher,
    )

    await mon.tick()

    # The LLM-raise path is handled inside ``_ask_llm`` (returns (False, ...)).
    # Ensure both positions were *attempted* — i.e. the loop did not abort.
    assert len(llm.calls) == 2
    assert position_exchange.close_calls == []


@pytest.mark.asyncio
async def test_insufficient_ohlcv_skipped() -> None:
    """<50 candles available → skip before LLM call, no close."""
    _factory, open_session = await build_sqlite_session_factory()
    await _seed(
        open_session,
        position=_open_position("BTC_USDT"),
        decision=_decision_with_invalidation(
            symbol="BTC_USDT",
            invalidation="Close below 90",
        ),
    )

    short = _ShortOhlcvExchange()
    fetcher = MultiTimeframeFetcher(
        exchange=short,  # type: ignore[arg-type]
        cache=InMemoryTTLCache(),
    )
    llm = _StubLLM()
    mon, position_exchange = _build_monitor(
        open_session=open_session,
        llm=llm,
        exchange=short,
        multi_tf_fetcher=fetcher,
    )

    await mon.tick()

    assert position_exchange.close_calls == []
    assert llm.calls == []  # LLM skipped when snapshot warm-up fails
    assert short.fetch_ohlcv_calls  # fetch was attempted
