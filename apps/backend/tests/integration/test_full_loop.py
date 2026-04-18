"""Full-loop integration test — one ``run_cycle`` → 3 WS event types observed.

Uses in-memory SQLite + FakeExchange + canned think/execute/reflect functions
so the outer ``trading_loop.run_cycle`` flow executes end-to-end without any
network I/O or LLM call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.api.container import build_api_container
from omnitrade.application.events import (
    EVENT_ACCOUNT_UPDATE,
    EVENT_DECISION_UPDATE,
    EVENT_POSITION_UPDATE,
)
from omnitrade.application.monitors.account_recorder_monitor import AccountRecorderMonitor
from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
from omnitrade.application.trading_loop import ExchangeObserveFn
from omnitrade.config import Settings
from omnitrade.domain.entities import (
    AccountSnapshot,
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)
from tests.application._fakes import FakeExchange, build_sqlite_session_factory, make_trade


@pytest.mark.asyncio
async def test_full_loop_emits_three_event_types() -> None:
    """Single iteration of trading_loop + account_recorder yields 3 event types."""
    factory, open_session = await build_sqlite_session_factory()
    fake_balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    open_trade = make_trade(order_id="open-1", ttype="open", price=Decimal("100"))
    fake_exchange = FakeExchange(
        balance=fake_balance,
        positions=[],
        place_order_trade=open_trade,
        close_trade=make_trade(order_id="close-1", ttype="close"),
    )

    settings = Settings(environment="testnet")
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]
    container.account_service._session_factory = open_session  # type: ignore[attr-defined]
    container.decision_service._session_factory = open_session  # type: ignore[attr-defined]
    container.position_manager._session_factory = open_session  # type: ignore[attr-defined]

    seen: dict[str, int] = {
        EVENT_POSITION_UPDATE: 0,
        EVENT_DECISION_UPDATE: 0,
        EVENT_ACCOUNT_UPDATE: 0,
    }

    async def on_event_factory(name):  # type: ignore[no-untyped-def]
        async def _inner(_payload):  # type: ignore[no-untyped-def]
            seen[name] += 1

        return _inner

    for name in seen:
        container.event_bus.subscribe(name, await on_event_factory(name))

    # --- build monitor + cassette fns ---------------------------------- #

    async def exchange_observe() -> MarketSnapshot:
        balance = await fake_exchange.fetch_balance()
        return MarketSnapshot(
            timestamp=datetime.now(tz=UTC),
            symbols=["BTC_USDT"],
            tickers={"BTC_USDT": Decimal("100")},
            positions=list[Position]([]),
            account=balance,
        )

    observe_typed: ExchangeObserveFn = exchange_observe

    async def news_gather() -> list[NewsItem]:
        return []

    async def think_fn(_market: MarketSnapshot, _news: list[NewsItem]) -> Decision:
        return Decision(
            action="open",
            symbol="BTC_USDT",
            side="long",
            size=Decimal("1"),
            leverage=5,
            confidence=Decimal("0.8"),
            reasoning="cassette",
        )

    async def risk_check(decision: Decision, _positions: list[Position]) -> Decision:
        return decision

    async def execute_fn(decision: Decision) -> list[Trade]:
        if decision.action != "open":
            return []
        trade = await container.position_manager.open_position(
            symbol=decision.symbol or "BTC_USDT",
            side=decision.side or "long",
            size=decision.size or Decimal("1"),
            leverage=decision.leverage or 5,
        )
        return [trade]

    async def reflect_fn(_decision: Decision, _trades: list[Trade]) -> None:
        return None

    monitor = TradingLoopMonitor(
        interval_minutes=20,
        exchange_observe=observe_typed,
        news_gather=news_gather,
        think_fn=think_fn,
        risk_check=risk_check,
        execute_fn=execute_fn,
        reflect_fn=reflect_fn,
        decision_service=container.decision_service,
    )
    recorder = AccountRecorderMonitor(
        interval_minutes=1,
        account_service=container.account_service,
    )

    await monitor.tick()
    await recorder.tick()

    assert seen[EVENT_POSITION_UPDATE] >= 1
    assert seen[EVENT_DECISION_UPDATE] >= 1
    assert seen[EVENT_ACCOUNT_UPDATE] >= 1
