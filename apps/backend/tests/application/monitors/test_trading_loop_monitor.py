"""TradingLoopMonitor — composition over run_cycle + decision persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.decision_service import DecisionService
from omnitrade.application.events import EventBus
from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
from omnitrade.application.trading_loop import make_empty_account_snapshot
from omnitrade.domain.entities import (
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from tests.application._fakes import FakeClock, build_sqlite_session_factory, make_trade


@pytest.mark.asyncio
async def test_tick_records_decision_and_increments_iteration() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    bus = EventBus()
    decision_service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=bus,
    )

    market = MarketSnapshot(
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        symbols=["BTC"],
        tickers={"BTC": Decimal("100")},
        account=make_empty_account_snapshot(Decimal("1000")),
        positions=[],
    )

    async def exchange_observe() -> MarketSnapshot:
        return market

    async def news_gather() -> list[NewsItem]:
        return []

    async def think_fn(_: MarketSnapshot, __: list[NewsItem]) -> Decision:
        return Decision(action="hold", reasoning="test")

    async def risk_check(dec: Decision, _: list[Position]) -> Decision:
        return dec

    async def execute_fn(_: Decision) -> list[Trade]:
        return [make_trade(order_id="ord-x", ttype="open")]

    async def reflect_fn(_: Decision, __: list[Trade]) -> None:
        return None

    clock = FakeClock(start=datetime(2026, 4, 18, 12, 0, tzinfo=UTC))
    mon = TradingLoopMonitor(
        interval_minutes=20,
        exchange_observe=exchange_observe,
        news_gather=news_gather,
        think_fn=think_fn,
        risk_check=risk_check,
        execute_fn=execute_fn,
        reflect_fn=reflect_fn,
        decision_service=decision_service,
        clock=clock,
    )
    assert mon.interval_seconds == 1200.0

    await mon.tick()
    await mon.tick()

    # Two decisions persisted, iteration counter advanced.
    from omnitrade.infrastructure.persistence.repositories.decision_repository import (
        DecisionRepository as R,
    )

    session = await open_session()
    try:
        recent = await R().list_recent(session)
    finally:
        await session.close()
    assert [d.iteration for d in recent] == [2, 1]
    assert recent[0].decision == "hold"
