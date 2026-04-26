"""Agno Agent-based think function — the production think path.

Returns a `(MarketSnapshot, list[NewsItem]) -> Decision` callable that
`composition._build_base_think_fn` wires into the trading loop.

Architecture:
    Agno Agent
      ├─ model        = agno.models.deepseek.DeepSeek("deepseek-reasoner")
      ├─ instructions = format_system_prompt(strategy, ...) verbatim
      ├─ tools        = [MultiMCPTools(2 servers), <4 decision recorders>]
      └─ run          = agent.arun(user_prompt) → DecisionRecorder.decision

The DecisionRecorder pattern lets the LLM "vote" via tool call without
side-effecting the exchange. Real trade execution stays in the
post-think pipeline (risk_check → execute → reflect). The Decision shape
is the contract — downstream RiskService / executor never see a tool call.

Optional Team advisory:
    When ``settings.multi_agent_enabled`` is true AND the active strategy
    is one of ``AGGRESSIVE_TEAM`` (raider squad) / ``MULTI_AGENT_CONSENSUS``
    (tribunal), an Agno ``Team`` runs first and produces a directional
    verdict. The verdict is injected into the main Agent's user prompt as
    advisory context — it does NOT replace the Decision. The single Agno
    Agent remains the only producer of the final ``Decision``. Team
    failures soft-degrade: a warning is logged and the Agent runs without
    advisory rather than failing the cycle.

Lifecycle:
    The MCP bridge is created once per think-fn factory call and held in
    closure. ``mcp_bridge`` is exposed as an attribute on the returned
    callable so the FastAPI lifespan can call ``await fn.mcp_bridge.close()``
    on shutdown rather than relying on process exit to reap subprocesses.
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
from omnitrade.agents.tools.mcp_bridge import AgnoMCPBridge
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.domain.enums import StrategyName
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

_TEAM_ELIGIBLE_STRATEGIES: frozenset[StrategyName] = frozenset(
    {StrategyName.AGGRESSIVE_TEAM, StrategyName.MULTI_AGENT_CONSENSUS}
)
"""Only these two strategies have prompt rosters wired in
`agents/prompts/multi_agent/`. Other strategies fall through even when
`MULTI_AGENT_ENABLED=true`."""

_TEAM_RUN_TIMEOUT_SECONDS: float = 60.0
"""Hard cap on the advisory Team call. Coordinator + members can issue
4-5 LLM calls; this keeps a slow upstream from blocking the main Agent
beyond the per-cycle budget. On timeout we soft-degrade to no advisory."""

_AGENT_RETRIES: int = 2
"""Per-cycle Agno-native retries on transient LLM failures (HTTP 5xx,
parser hiccups). With ``exponential_backoff=True`` each retry doubles
its wait. The outer ``_TEAM_RUN_TIMEOUT_SECONDS`` and the cycle's own
``asyncio.Lock`` still bound the worst-case wall-clock budget."""


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
    strategy: StrategyName,
    market_block_builder: Callable[[Any, MarketSnapshot], Awaitable[str]],
    recent_trades_block_builder: Callable[[Any], Awaitable[str]],
) -> ThinkFn:
    """Return a `think_fn` backed by Agno's Agent.

    Decoupled from `composition.py` internals via the four collaborator
    callables (render_messages, market_block_builder, recent_trades_block_builder)
    + the resolved StrategyName. This makes the function easy to unit-test
    with stub renderers.

    The returned callable exposes ``mcp_bridge`` as an attribute so the
    FastAPI lifespan can shut down the spawned MCP subprocesses cleanly
    on application teardown.
    """
    bridge = AgnoMCPBridge()
    bridge_lock = asyncio.Lock()
    # Built once at factory time — reused across every cycle so Agno's
    # session table sees one logical trading session, not one per tick.
    session_db = _build_session_db(settings)

    # Team advisory state — only populated when MULTI_AGENT_ENABLED + the
    # strategy is one of the two team-eligible rosters. Lazy-built on
    # first cycle (and cached in closure) so a misconfigured team never
    # crashes startup; subsequent failures fall through to the warn path
    # in the per-cycle handler below.
    team_advisory_enabled = (
        settings.multi_agent_enabled and strategy in _TEAM_ELIGIBLE_STRATEGIES
    )
    team_holder: dict[str, Any] = {"team": None, "build_failed": False}

    async def _ensure_mcp_connected() -> None:
        if bridge._toolset is not None:
            return
        async with bridge_lock:
            if bridge._toolset is None:
                await bridge.connect()

    def _build_team_once() -> Any:
        """Lazy-build the Team on first cycle, cache in closure.

        Returns ``None`` and flips ``build_failed`` on construction error
        so we don't repeatedly retry a busted import / config.
        """
        if team_holder["team"] is not None or team_holder["build_failed"]:
            return team_holder["team"]
        try:
            from omnitrade.agents.experts_team import build_agno_team

            extra_tools: list[Any] = []
            if bridge._toolset is not None:
                extra_tools.append(bridge._toolset)
            team = build_agno_team(strategy, settings, extra_tools=extra_tools)
            team_holder["team"] = team
            with_context(logger).info(
                "trading_agent.team_advisory.built",
                strategy=str(strategy),
            )
        except Exception as exc:
            team_holder["build_failed"] = True
            with_context(logger).warning(
                "trading_agent.team_advisory.build_failed",
                strategy=str(strategy),
                error=str(exc),
            )
        return team_holder["team"]

    async def _team_advisory_text(user_prompt: str) -> str | None:
        """Run the advisory Team and return its verdict text, or None.

        Soft-degrade contract: any failure (build / timeout / runtime)
        returns ``None`` so the main Agent still produces the cycle's
        Decision. The team output is **advisory only** — it does not
        replace or short-circuit the Decision contract.
        """
        team = _build_team_once()
        if team is None:
            return None
        try:
            run = await asyncio.wait_for(
                team.arun(user_prompt),
                timeout=_TEAM_RUN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            with_context(logger).warning(
                "trading_agent.team_advisory.timeout",
                timeout_s=_TEAM_RUN_TIMEOUT_SECONDS,
            )
            return None
        except Exception as exc:
            with_context(logger).warning(
                "trading_agent.team_advisory.run_failed",
                error=str(exc),
            )
            return None

        text = str(getattr(run, "content", "") or "").strip()
        if not text:
            with_context(logger).warning("trading_agent.team_advisory.empty_output")
            return None
        return text

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
        except Exception as exc:
            with_context(logger).warning(
                "trading_agent.mcp_unavailable",
                error=str(exc),
            )

        # Optional Team advisory — runs BEFORE the main Agent so its verdict
        # can appear in the Agent's user prompt as advisory context. The
        # Team never produces a Decision: that contract belongs to the
        # main Agent's DecisionRecorder tool calls. Soft-degrades on any
        # team error so a flaky panel never breaks the cycle.
        if team_advisory_enabled:
            advisory = await _team_advisory_text(user_prompt)
            if advisory:
                user_prompt = (
                    "[Team advisory — informational only; you remain the "
                    "sole decision-maker and MUST still call exactly one "
                    f"decision tool]\n{advisory}\n\n[Situation report]\n"
                    + user_prompt
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
            # Agno-native retry on transient LLM failures. The outer
            # _TEAM_RUN_TIMEOUT_SECONDS budget still applies, so a
            # flapping upstream cannot pile up retries past the cycle
            # cap.
            "retries": _AGENT_RETRIES,
            "exponential_backoff": True,
        }
        if session_db is not None:
            # Persist this cycle as a run inside the shared trading session
            # and surface the last N runs back into the Agent's context so
            # the LLM has cross-cycle continuity (Stage D of the cutover).
            agent_kwargs["db"] = session_db
            agent_kwargs["session_id"] = _TRADING_SESSION_ID
            agent_kwargs["add_history_to_context"] = True
            agent_kwargs["num_history_runs"] = _NUM_HISTORY_RUNS
            # T2: ask Agno to write per-session rolling summaries to the
            # `ai.agno_sessions.summary` column. The summary is fed back
            # into the LLM context on subsequent runs in the same
            # session, which gives the trading agent a longer effective
            # memory than ``num_history_runs`` alone (5 cycles raw + a
            # narrative summary stretching further back).
            agent_kwargs["enable_session_summaries"] = True

        agent = Agent(**agent_kwargs)

        with_context(logger).info(
            "trading_agent.run",
            model=settings.agno_llm_model,
            n_tools=len(tools_for_agent),
            mcp_connected=bridge._toolset is not None,
            history_runs=_NUM_HISTORY_RUNS if session_db is not None else 0,
        )

        try:
            run_result = await agent.arun(user_prompt)
        except Exception as exc:
            with_context(logger).error(
                "trading_agent.run_failed",
                error=str(exc),
            )
            return Decision(
                action="hold",
                reasoning=f"agno_agent_run_failed: {exc!r}",
            )

        if recorder.decision is not None:
            return recorder.decision

        # No decision tool fired — fall through to a defensive hold so a
        # failed cycle still produces a row downstream observers can see.
        text = str(getattr(run_result, "content", "") or "")[:512]
        with_context(logger).warning(
            "trading_agent.no_decision_tool_fired",
            run_text_head=text[:120],
        )
        return Decision(
            action="hold",
            reasoning=text or "agno_agent: no decision tool fired (defaulting to hold)",
        )

    # Surface the MCP bridge so the FastAPI lifespan can close subprocesses
    # cleanly. ``ThinkFn`` is a plain callable; setting an attribute on a
    # closure is safe and lets the trading-monitor wiring stay opaque to
    # bridge mechanics.
    think_fn.mcp_bridge = bridge  # type: ignore[attr-defined]
    return think_fn


__all__ = ["ThinkFn", "build_agno_think_fn"]
