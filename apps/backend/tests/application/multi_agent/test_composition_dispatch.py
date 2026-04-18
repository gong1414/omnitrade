"""Composition-level roster dispatch tests (Phase 8.5a).

Pins ``build_think_fn``'s 8.5a expansion:

  * ``multi_agent_enabled=False`` → ``tool_registry`` is left untouched
    regardless of strategy. The single-agent path remains byte-exact with
    the 22/22 characterization gate.
  * ``multi_agent_enabled=True`` + ``AGGRESSIVE_TEAM`` → 4 expert tools
    registered.
  * ``multi_agent_enabled=True`` + ``MULTI_AGENT_CONSENSUS`` → 3 juror
    tools registered.
  * ``multi_agent_enabled=True`` + non-multi strategy (e.g. BALANCED) →
    registry untouched (no-op, no raise).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.think_node import ToolRegistry
from omnitrade.application.multi_agent.composition import build_think_fn
from omnitrade.config import Settings
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache


class _StubExchange:
    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int = 100,
    ) -> list[list[float]]:
        return [[0.0, 1.0, 1.0, 1.0, 1.0, 10.0]]


class _StubLLM:
    async def complete(self, **_kwargs: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "{}"}}]}


def _make_fetcher() -> MultiTimeframeFetcher:
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    return MultiTimeframeFetcher(
        exchange=_StubExchange(),  # type: ignore[arg-type]
        cache=cache,
    )


def _make_market() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("68000")},
    )


async def _base_think(_m: MarketSnapshot, _n: list[NewsItem]) -> Decision:
    return Decision(action="hold", reasoning="")


@pytest.mark.asyncio
async def test_flag_off_leaves_tool_registry_empty() -> None:
    settings = Settings(multi_agent_enabled=False)
    registry = ToolRegistry()
    build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.AGGRESSIVE_TEAM,
        tool_registry=registry,
        llm=_StubLLM(),  # type: ignore[arg-type]
    )
    assert registry.names() == []


@pytest.mark.asyncio
async def test_flag_on_aggressive_team_registers_4_experts() -> None:
    settings = Settings(multi_agent_enabled=True)
    registry = ToolRegistry()
    build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.AGGRESSIVE_TEAM,
        tool_registry=registry,
        llm=_StubLLM(),  # type: ignore[arg-type]
    )
    assert set(registry.names()) == {
        "trendExpert",
        "predictionExpert",
        "moneyFlowExpert",
        "riskControlExpert",
    }


@pytest.mark.asyncio
async def test_flag_on_multi_agent_consensus_registers_3_jurors() -> None:
    settings = Settings(multi_agent_enabled=True)
    registry = ToolRegistry()
    build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.MULTI_AGENT_CONSENSUS,
        tool_registry=registry,
        llm=_StubLLM(),  # type: ignore[arg-type]
    )
    assert set(registry.names()) == {
        "technicalAnalyst",
        "trendAnalyst",
        "riskAssessor",
    }


@pytest.mark.asyncio
async def test_flag_on_balanced_is_noop() -> None:
    """``MULTI_AGENT_ENABLED=true`` + non-multi strategy must not register tools."""
    settings = Settings(multi_agent_enabled=True)
    registry = ToolRegistry()
    build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.BALANCED,
        tool_registry=registry,
        llm=_StubLLM(),  # type: ignore[arg-type]
    )
    assert registry.names() == []


@pytest.mark.asyncio
async def test_no_tool_registry_still_returns_base_think_when_multi_tf_off() -> None:
    """Passing ``tool_registry=None`` preserves the 8.1 passthrough contract."""
    settings = Settings(multi_agent_enabled=False, multi_timeframe_enabled=False)
    think_fn = build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.AGGRESSIVE_TEAM,
    )
    assert think_fn is _base_think


@pytest.mark.asyncio
async def test_no_llm_with_flag_on_skips_registration() -> None:
    """If ``llm=None`` is passed, registration is skipped (defensive)."""
    settings = Settings(multi_agent_enabled=True)
    registry = ToolRegistry()
    build_think_fn(
        _base_think,
        _make_fetcher(),
        settings,
        strategy_selector=lambda: StrategyName.AGGRESSIVE_TEAM,
        tool_registry=registry,
        llm=None,
    )
    assert registry.names() == []
