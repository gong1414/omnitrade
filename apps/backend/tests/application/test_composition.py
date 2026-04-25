"""Unit tests for ``application.composition`` market-block helpers.

The end-to-end ``build_trading_monitor`` tick test that lived here drove
the legacy LangGraph LLMClient stub. After Stage A of the Agno cutover
(`/Users/daoyu/.claude/plans/mossy-frolicking-hickey.md`) the Agent owns
its own DeepSeek client internally, so a fake ``LLMClient.complete`` is
no longer reachable. The end-to-end coverage is rebuilt against the
Agno Agent in Stage E.

Today this file only exercises the market-block fallback paths — those
are pure-Python helpers that don't depend on any LLM machinery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.api.container import build_api_container
from omnitrade.application.composition import _build_market_block
from omnitrade.config import Settings
from omnitrade.domain.entities import AccountSnapshot, MarketSnapshot
from tests.application._fakes import (
    FakeExchange,
    build_sqlite_session_factory,
)


@pytest.mark.asyncio
async def test_build_market_block_emits_indicator_table() -> None:
    """The rich market block contains the indicator table header + data rows."""
    factory, open_session = await build_sqlite_session_factory()
    balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    fake_exchange = FakeExchange(balance=balance, positions=[])
    settings = Settings(
        environment="testnet",
        trading_strategy="arena-autopilot",
        trading_symbols=["BTC_USDT", "ETH_USDT"],
    )
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT", "ETH_USDT"],
        tickers={"BTC_USDT": Decimal("100"), "ETH_USDT": Decimal("100")},
        account=balance,
        positions=[],
    )

    block = await _build_market_block(container, market)

    assert "15m EMA20/50/200" in block
    assert "15m RSI14" in block
    assert "Volx" in block
    assert "BTC_USDT" in block
    assert "ETH_USDT" in block
    assert "Recent 15m closes" in block


@pytest.mark.asyncio
async def test_build_market_block_falls_back_when_no_symbols() -> None:
    """Empty ticker + symbols set → legacy (no data) string, no crash."""
    factory, open_session = await build_sqlite_session_factory()
    fake_exchange = FakeExchange(balance=None, positions=[])
    settings = Settings(environment="testnet", trading_symbols=[])
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=[],
        tickers={},
        positions=[],
    )

    block = await _build_market_block(container, market)
    assert block == "(no data)"


@pytest.mark.asyncio
async def test_build_market_block_degrades_on_fetcher_exception() -> None:
    """When the multi-TF fetcher raises, fall back to the ticker summary."""
    factory, open_session = await build_sqlite_session_factory()
    balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    fake_exchange = FakeExchange(balance=balance, positions=[])
    settings = Settings(
        environment="testnet",
        trading_symbols=["BTC_USDT"],
    )
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    async def _boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("network went poof")

    container.multi_tf_fetcher.fetch_ohlcv_multi_tf = _boom  # type: ignore[method-assign]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("100")},
        account=balance,
        positions=[],
    )

    block = await _build_market_block(container, market)
    assert "BTC_USDT: 100" in block
    assert "EMA20/50/200" not in block
