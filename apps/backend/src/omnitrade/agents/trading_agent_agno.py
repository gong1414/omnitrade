"""Agno Agent-based think function — the only think path after Stage A.

Returns a `(MarketSnapshot, list[NewsItem]) -> Decision` callable that
`composition._build_base_think_fn` wires into the trading loop.

Architecture:
    Agno Agent
      ├─ model        = agno.models.deepseek.DeepSeek("deepseek-reasoner")
      ├─ instructions = format_system_prompt(strategy, ...) verbatim
      ├─ tools        = [MultiMCPTools(2 servers), <4 decision recorders>]
      └─ run          = agent.arun(user_prompt) → DecisionRecorder.decision

The DecisionRecorder pattern lets the LLM "vote" via tool call without
side-effecting the exchange. Real trade execution stays in step 5 of the
trading loop. This keeps Phase 2 additive — same Decision shape, same
output contract, no behavior change to downstream RiskService / executor.

Lifecycle:
    The MCP bridge is created once per think-fn factory call and held in
    closure. It's connected lazily on first cycle and stays open for the
    process lifetime. The OS cleans up subprocesses on shutdown.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from omnitrade.config import Settings

from agno.agent import Agent
from agno.models.deepseek import DeepSeek

from omnitrade.agents.tools.decision_schemas import (
    DecisionRecorder,
    build_decision_tools,
)
from omnitrade.agents.tools.mcp_bridge_agno import AgnoMCPBridge
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


ThinkFn = Callable[[MarketSnapshot, list[NewsItem]], Awaitable[Decision]]


def _strip_provider_prefix(model_id: str) -> str:
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def _resolve_deepseek(settings: Settings) -> DeepSeek:
    """Build the DeepSeek model from Settings.

    Honours `agno_llm_model` (defaults to `deepseek-reasoner` per spec
    exception E2) and the existing LLM_API_KEY / DEEPSEEK_API_KEY surface.
    """
    model_id = _strip_provider_prefix(settings.agno_llm_model)
    api_key: str | None = None
    if settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value()
    elif settings.deepseek_api_key is not None:
        api_key = settings.deepseek_api_key.get_secret_value()
    base_url = str(settings.llm_base_url) if settings.llm_base_url is not None else None

    kwargs: dict[str, Any] = {"id": model_id}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return DeepSeek(**kwargs)


_TRADING_SESSION_ID = "omnitrade-trading"
"""Stable session id shared across cycles so Agno persists every run as
part of one logical trading conversation. With `add_history_to_context=True`
this is what gives the LLM continuity across `tick()`s."""

_NUM_HISTORY_RUNS = 5
"""How many previous cycles' worth of run history Agno surfaces back into
each new run's context. Five cycles ≈ 100 minutes at the default 20-min
cadence — long enough to catch a regime shift, short enough to keep the
prompt budget bounded."""


def _build_session_db(settings: Settings) -> Any:
    """Construct the optional Agno session DB from `agno_postgres_url`.

    Returns `None` when the URL is unset so single-process / test runs
    don't pull psycopg into the Agent path.
    """
    if not settings.agno_postgres_url:
        return None
    # Lazy import — psycopg only matters when Postgres is actually wired.
    from agno.db.postgres import PostgresDb

    return PostgresDb(db_url=settings.agno_postgres_url)


def build_agno_think_fn(
    container: Any,
    settings: Settings,
    *,
    render_messages: Callable[..., list[dict[str, str]]],
    strategy: Any,
    market_block_builder: Callable[[Any, MarketSnapshot], Awaitable[str]],
    recent_trades_block_builder: Callable[[Any], Awaitable[str]],
) -> ThinkFn:
    """Return a `think_fn` backed by Agno's Agent.

    Decoupled from `composition.py` internals via the four collaborator
    callables (render_messages, market_block_builder, recent_trades_block_builder)
    + the resolved StrategyName. This makes the function easy to unit-test
    with stub renderers.
    """
    bridge = AgnoMCPBridge()
    bridge_lock = asyncio.Lock()
    # Built once at factory time — reused across every cycle so Agno's
    # session table sees one logical trading session, not one per tick.
    session_db = _build_session_db(settings)

    async def _ensure_mcp_connected() -> None:
        if bridge._toolset is not None:
            return
        async with bridge_lock:
            if bridge._toolset is None:
                await bridge.connect()

    async def think_fn(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        positions = list(market.positions)
        market_block = await market_block_builder(container, market)
        recent_trades_block = await recent_trades_block_builder(container)
        messages = render_messages(
            strategy=strategy,
            market=market,
            news=news,
            positions=positions,
            settings=settings,
            iteration=0,
            minutes_elapsed=0,
            market_data_block=market_block,
            recent_trades_block=recent_trades_block,
        )
        # Split system + user from the rendered messages list.
        system_prompt = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_prompt = next((m["content"] for m in messages if m.get("role") == "user"), "")

        # Per-cycle DecisionRecorder. Fresh recorder per cycle ⇒ no cross-talk
        # between concurrent triggers.
        recorder = DecisionRecorder()
        decision_tools = build_decision_tools(recorder)

        try:
            await _ensure_mcp_connected()
        except Exception as exc:  # noqa: BLE001 — degrade to no-MCP rather than fail
            with_context(logger).warning(
                "trading_agent_agno.mcp_unavailable",
                error=str(exc),
            )

        # Tools: MCP toolkit (info tools) first, decision recorders last
        # so the LLM consumes context before deciding (mirrors PR-B2 ordering
        # rationale in `trade_execution.build_hold_tool` docstring).
        tools_for_agent: list[Any] = []
        if bridge._toolset is not None:
            tools_for_agent.append(bridge._toolset)
        tools_for_agent.extend(decision_tools)

        agent_kwargs: dict[str, Any] = {
            "model": _resolve_deepseek(settings),
            "instructions": system_prompt,
            "tools": tools_for_agent,
            "telemetry": False,
        }
        if session_db is not None:
            # Persist this cycle as a run inside the shared trading session
            # and surface the last N runs back into the Agent's context so
            # the LLM has cross-cycle continuity (Stage D of the cutover).
            agent_kwargs["db"] = session_db
            agent_kwargs["session_id"] = _TRADING_SESSION_ID
            agent_kwargs["add_history_to_context"] = True
            agent_kwargs["num_history_runs"] = _NUM_HISTORY_RUNS

        agent = Agent(**agent_kwargs)

        with_context(logger).info(
            "trading_agent_agno.run",
            model=settings.agno_llm_model,
            n_tools=len(tools_for_agent),
            mcp_connected=bridge._toolset is not None,
            history_runs=_NUM_HISTORY_RUNS if session_db is not None else 0,
        )

        try:
            run_result = await agent.arun(user_prompt)
        except Exception as exc:  # noqa: BLE001 — Phase 2 must not crash the cycle
            with_context(logger).error(
                "trading_agent_agno.run_failed",
                error=str(exc),
            )
            return Decision(
                action="hold",
                reasoning=f"agno_agent_run_failed: {exc!r}",
            )

        if recorder.decision is not None:
            return recorder.decision

        # No decision tool fired — fall through to a defensive hold.
        # In legacy LangGraph this raises ToolCallRequiredError when
        # tool_choice='required'; for Phase 2 we degrade gracefully so a
        # failed cycle still produces a row downstream observers can see.
        text = str(getattr(run_result, "content", "") or "")[:512]
        with_context(logger).warning(
            "trading_agent_agno.no_decision_tool_fired",
            run_text_head=text[:120],
        )
        return Decision(
            action="hold",
            reasoning=text or "agno_agent: no decision tool fired (defaulting to hold)",
        )

    return think_fn


__all__ = ["ThinkFn", "build_agno_think_fn"]
