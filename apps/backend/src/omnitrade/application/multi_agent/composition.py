"""``build_think_fn`` — compose a ``ThinkFn`` with multi-TF + multi-agent roster.

Phase 8.1 scope (passthrough enricher):
  * If ``settings.multi_timeframe_enabled`` is False, return ``base_think``
    unchanged — v1 path is byte-exact.
  * Otherwise wrap ``base_think`` so that before delegating, the wrapper
    fetches multi-TF OHLCV for every symbol in the ``MarketSnapshot`` and
    attaches it to ``MarketSnapshot.multi_tf_ohlcv``.

Phase 8.5a scope (roster dispatch, CRITICAL-2):
  * If ``settings.multi_agent_enabled`` is True AND the active strategy is
    ``AGGRESSIVE_TEAM`` or ``MULTI_AGENT_CONSENSUS``, and an optional
    ``tool_registry`` is supplied, register the strategy-specific roster
    into the registry before the ``ThinkFn`` is invoked.
  * No ``langgraph`` import (grep-gated — MINOR-3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from omnitrade.application.trading_loop import ThinkFn
from omnitrade.config import Settings
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient
from omnitrade.domain.services.tf_strategy_map import timeframes_for
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


_MULTI_AGENT_STRATEGIES: frozenset[StrategyName] = frozenset(
    {StrategyName.AGGRESSIVE_TEAM, StrategyName.MULTI_AGENT_CONSENSUS}
)


def build_think_fn(
    base_think: ThinkFn,
    fetcher: MultiTimeframeFetcher,
    settings: Settings,
    *,
    strategy_selector: Callable[[], StrategyName],
    tool_registry: Any | None = None,
    llm: LLMClient | None = None,
) -> ThinkFn:
    """Return a ``ThinkFn`` that optionally enriches the cycle with multi-TF + roster.

    Args:
        base_think: The underlying ``ThinkFn`` (LangGraph think node wrapper).
        fetcher: Per-cycle multi-TF fetcher injected from the DI container.
        settings: Runtime configuration — read ``multi_timeframe_enabled``
            and ``multi_agent_enabled`` as rollback kill-switches.
        strategy_selector: Zero-arg callable returning the active
            ``StrategyName`` (lets the caller change strategy at runtime
            without rebuilding the ``ThinkFn``).
        tool_registry: Optional ``ToolRegistry`` to extend with the
            strategy-specific multi-agent roster. When None or when
            ``settings.multi_agent_enabled`` is False, roster registration
            is skipped.
        llm: Optional ``LLMClient`` used for sub-agent calls. Required
            when ``tool_registry`` is supplied and
            ``settings.multi_agent_enabled`` is True.

    Returns:
        Either ``base_think`` unchanged (both kill-switches off) or a
        wrapper that performs enrichment/registration before delegating.
    """
    # 8.5a — roster registration runs once at build time (not per-cycle) so
    # the main-agent's tool-calling loop sees the expert/juror handlers
    # registered before any LLM invocation.
    if settings.multi_agent_enabled and tool_registry is not None and llm is not None:
        _register_roster_tools(
            tool_registry=tool_registry,
            strategy=strategy_selector(),
            llm=llm,
            settings=settings,
        )

    if not settings.multi_timeframe_enabled:
        return base_think

    async def _enriched(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        strategy = strategy_selector()
        tfs = timeframes_for(strategy)
        per_symbol: dict[str, dict[str, list[Any]]] = {}
        for raw_symbol in market.symbols:
            try:
                sym = Symbol(value=raw_symbol)
            except (ValueError, TypeError) as exc:
                with_context(logger).warning(
                    "market_data.multi_tf.skip_symbol",
                    symbol=raw_symbol,
                    error=str(exc),
                )
                continue
            fetched = await fetcher.fetch(sym, tfs)
            per_symbol[sym.value] = dict(fetched)

        enriched = market.model_copy(update={"multi_tf_ohlcv": per_symbol})
        with_context(logger).info(
            "multi_agent.composition.enriched",
            strategy=str(strategy),
            n_symbols=len(per_symbol),
            n_tfs=len(tfs),
        )
        return await base_think(enriched, news)

    return _enriched


def _register_roster_tools(
    *,
    tool_registry: Any,
    strategy: StrategyName,
    llm: LLMClient,
    settings: Settings,
) -> None:
    """Extend ``tool_registry`` with the strategy-specific multi-agent roster.

    No-op when ``strategy`` isn't one of the two multi-agent strategies,
    so a misconfigured ``MULTI_AGENT_ENABLED=true`` + BALANCED cycle still
    falls through to the single-agent path instead of raising.
    """
    if strategy not in _MULTI_AGENT_STRATEGIES:
        with_context(logger).info(
            "multi_agent.composition.roster_skip_non_multi_strategy",
            strategy=str(strategy),
        )
        return

    # Local import keeps ``composition`` importable without langchain when
    # the roster path is not exercised (e.g. by the 8.1 passthrough tests).
    from omnitrade.application.multi_agent.roster import roster_for_strategy

    roster = roster_for_strategy(strategy, llm=llm, settings=settings)
    for tool in roster:
        # StructuredTool.ainvoke wraps the coroutine with arg validation;
        # ToolRegistry handlers expect ``(dict) -> dict`` so we adapt.
        tool_name: str = tool.name

        async def _handler(args: dict[str, Any], _t: Any = tool) -> dict[str, Any]:
            result = await _t.ainvoke(args)
            if isinstance(result, dict):
                return result
            return {"result": result}

        tool_registry.register(tool_name, _handler)

    with_context(logger).info(
        "multi_agent.composition.roster_registered",
        strategy=str(strategy),
        n_tools=len(roster),
        names=[t.name for t in roster],
    )


__all__ = ["build_think_fn"]
