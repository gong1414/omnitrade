"""Unit tests for the pure-asyncio outer trading loop.

These tests MUST run without importing langgraph at the orchestration
level — the think step is injected as a plain ``async def``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.trading_loop import (
    LoopOutcome,
    execute_trades,
    gather_news,
    make_empty_account_snapshot,
    observe_market,
    reflect,
    run_cycle,
    think,
    validate_decision,
)
from omnitrade.domain.entities import (
    Decision,
    MarketSnapshot,
    NewsItem,
    Position,
    Trade,
)


def _snap(symbols: list[str]) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2026, 4, 17, tzinfo=UTC),
        symbols=symbols,
        tickers={s: Decimal("100") for s in symbols},
        account=make_empty_account_snapshot(Decimal("1000")),
        positions=[],
    )


def _news(n: int) -> list[NewsItem]:
    base = datetime(2026, 4, 17, 0, 0, tzinfo=UTC)
    return [
        NewsItem(
            source=f"src{i}",
            headline=f"hd{i}",
            summary="s",
            published_at=base.replace(minute=i),
            sentiment=None,
        )
        for i in range(n)
    ]


# ── individual steps ─────────────────────────────────────────────────── #


@pytest.mark.asyncio
async def test_observe_market_passthrough() -> None:
    async def fn() -> MarketSnapshot:
        return _snap(["BTC"])

    out = await observe_market(fn)
    assert out.symbols == ["BTC"]


@pytest.mark.asyncio
async def test_gather_news_swallows_exception() -> None:
    async def boom() -> list[NewsItem]:
        raise RuntimeError("mcp flaky")

    out = await gather_news(boom)
    assert out == []


@pytest.mark.asyncio
async def test_think_sorts_news_and_symbols() -> None:
    async def think_fn(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        # symbols are sorted ascending
        assert market.symbols == ["AAA", "BBB", "CCC"]
        # news are sorted newest-first
        assert [n.headline for n in news] == ["hd2", "hd1", "hd0"]
        return Decision(action="hold")

    market = _snap(["CCC", "AAA", "BBB"])
    news = _news(3)
    # feed news in reverse to prove the sort happens in think()
    out = await think(think_fn, market, list(reversed(news)))
    assert out.action == "hold"


@pytest.mark.asyncio
async def test_validate_decision_can_override() -> None:
    async def risk(decision: Decision, positions: list[Position]) -> Decision:
        # Force a hold regardless of the incoming decision
        return Decision(action="hold", reasoning="risk_override")

    d = await validate_decision(risk, Decision(action="open", symbol="BTC", side="long"), [])
    assert d.action == "hold"
    assert d.reasoning == "risk_override"


@pytest.mark.asyncio
async def test_execute_trades_skips_on_hold() -> None:
    called: list[Decision] = []

    async def exec_fn(d: Decision) -> list[Trade]:
        called.append(d)
        return []

    trades = await execute_trades(exec_fn, Decision(action="hold"))
    assert trades == []
    assert called == []


@pytest.mark.asyncio
async def test_execute_trades_dispatches_for_open() -> None:
    async def exec_fn(d: Decision) -> list[Trade]:
        return [
            Trade(
                order_id="o1",
                symbol=d.symbol or "",
                side=d.side or "long",
                type="open",
                price=Decimal("100"),
                quantity=Decimal("1"),
                leverage=d.leverage or 1,
                timestamp=datetime(2026, 4, 17, tzinfo=UTC),
            )
        ]

    trades = await execute_trades(
        exec_fn, Decision(action="open", symbol="BTC", side="long", leverage=5)
    )
    assert len(trades) == 1
    assert trades[0].symbol == "BTC"


@pytest.mark.asyncio
async def test_reflect_is_awaited() -> None:
    hits: list[int] = []

    async def reflect_fn(d: Decision, trades: list[Trade]) -> None:
        hits.append(len(trades))

    await reflect(reflect_fn, Decision(action="hold"), [])
    assert hits == [0]


# ── orchestrator (run_cycle) ────────────────────────────────────────── #


@pytest.mark.asyncio
async def test_run_cycle_deterministic_fanout() -> None:
    async def observe() -> MarketSnapshot:
        return _snap(["BTC", "ETH"])

    async def news() -> list[NewsItem]:
        return _news(2)

    async def think_fn(m: MarketSnapshot, n: list[NewsItem]) -> Decision:
        return Decision(action="open", symbol="BTC", side="long", leverage=3)

    async def risk(d: Decision, pos: list[Position]) -> Decision:
        return d

    async def exec_fn(d: Decision) -> list[Trade]:
        return [
            Trade(
                order_id="x",
                symbol=d.symbol or "",
                side=d.side or "long",
                type="open",
                price=Decimal("100"),
                quantity=Decimal("1"),
                leverage=d.leverage or 1,
                timestamp=datetime(2026, 4, 17, tzinfo=UTC),
            )
        ]

    async def reflect_fn(d: Decision, trades: list[Trade]) -> None:
        return None

    outcome: LoopOutcome = await run_cycle(
        exchange_observe=observe,
        news_gather=news,
        think_fn=think_fn,
        risk_check=risk,
        execute_fn=exec_fn,
        reflect_fn=reflect_fn,
    )
    assert outcome.decision.action == "open"
    assert len(outcome.trades) == 1
    assert outcome.market.symbols == ["BTC", "ETH"]
    assert outcome.started_at <= outcome.finished_at


@pytest.mark.asyncio
async def test_run_cycle_news_failure_is_non_fatal() -> None:
    async def observe() -> MarketSnapshot:
        return _snap(["BTC"])

    async def news() -> list[NewsItem]:
        raise RuntimeError("mcp down")

    async def think_fn(m: MarketSnapshot, n: list[NewsItem]) -> Decision:
        assert n == []
        return Decision(action="hold")

    async def risk(d: Decision, pos: list[Position]) -> Decision:
        return d

    async def exec_fn(d: Decision) -> list[Trade]:
        return []

    async def reflect_fn(d: Decision, trades: list[Trade]) -> None:
        return None

    outcome = await run_cycle(
        exchange_observe=observe,
        news_gather=news,
        think_fn=think_fn,
        risk_check=risk,
        execute_fn=exec_fn,
        reflect_fn=reflect_fn,
    )
    assert outcome.decision.action == "hold"
    assert outcome.news == []


@pytest.mark.asyncio
async def test_run_cycle_observe_failure_propagates() -> None:
    async def observe() -> MarketSnapshot:
        raise RuntimeError("exchange down")

    async def news() -> list[NewsItem]:
        return []

    async def think_fn(m: MarketSnapshot, n: list[NewsItem]) -> Decision:
        return Decision(action="hold")

    async def risk(d: Decision, pos: list[Position]) -> Decision:
        return d

    async def exec_fn(d: Decision) -> list[Trade]:
        return []

    async def reflect_fn(d: Decision, trades: list[Trade]) -> None:
        return None

    with pytest.raises(RuntimeError, match="exchange down"):
        await run_cycle(
            exchange_observe=observe,
            news_gather=news,
            think_fn=think_fn,
            risk_check=risk,
            execute_fn=exec_fn,
            reflect_fn=reflect_fn,
        )
