"""CRITICAL-1: monitor startup refuses USE_WS_MARKET_DATA + CASSETTE_MODE both on.

The assertion lives in ``TradingLoopMonitor.__init__`` (NOT in
``decision_service.py``). Flipping both flags must raise
``RuntimeError`` before any cycle runs.
"""

from __future__ import annotations

import pytest

from omnitrade.application.decision_service import DecisionService
from omnitrade.application.events.bus import EventBus
from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem, Position, Trade
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from tests.application._fakes import build_sqlite_session_factory


async def _noop_observe() -> MarketSnapshot:
    raise AssertionError("observe_market should not be called during __init__ assertion")


async def _noop_news() -> list[NewsItem]:
    return []


async def _noop_think(_m: MarketSnapshot, _n: list[NewsItem]) -> Decision:
    return Decision(action="hold")


async def _noop_risk(d: Decision, _p: list[Position]) -> Decision:
    return d


async def _noop_execute(_d: Decision) -> list[Trade]:
    return []


async def _noop_reflect(_d: Decision, _t: list[Trade]) -> None:
    return None


@pytest.mark.asyncio
async def test_monitor_rejects_ws_and_cassette_both_on() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    decision_service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=EventBus(),
    )
    with pytest.raises(RuntimeError, match="USE_WS_MARKET_DATA"):
        TradingLoopMonitor(
            interval_minutes=20,
            exchange_observe=_noop_observe,
            news_gather=_noop_news,
            think_fn=_noop_think,
            risk_check=_noop_risk,
            execute_fn=_noop_execute,
            reflect_fn=_noop_reflect,
            decision_service=decision_service,
            use_ws_market_data=True,
            cassette_mode=True,
        )


@pytest.mark.asyncio
async def test_monitor_accepts_ws_only() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    decision_service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=EventBus(),
    )
    mon = TradingLoopMonitor(
        interval_minutes=20,
        exchange_observe=_noop_observe,
        news_gather=_noop_news,
        think_fn=_noop_think,
        risk_check=_noop_risk,
        execute_fn=_noop_execute,
        reflect_fn=_noop_reflect,
        decision_service=decision_service,
        use_ws_market_data=True,
        cassette_mode=False,
    )
    assert mon._cassette_mode is False


@pytest.mark.asyncio
async def test_monitor_accepts_cassette_only() -> None:
    _factory, open_session = await build_sqlite_session_factory()
    decision_service = DecisionService(
        repo=DecisionRepository(),
        session_factory=open_session,
        event_bus=EventBus(),
    )
    mon = TradingLoopMonitor(
        interval_minutes=20,
        exchange_observe=_noop_observe,
        news_gather=_noop_news,
        think_fn=_noop_think,
        risk_check=_noop_risk,
        execute_fn=_noop_execute,
        reflect_fn=_noop_reflect,
        decision_service=decision_service,
        use_ws_market_data=False,
        cassette_mode=True,
    )
    assert mon._cassette_mode is True
