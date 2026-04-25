"""Agno Workflow scaffold for the 6-step trading cycle (Phase 3).

The legacy orchestrator at `application/trading_loop.py::TradingLoopMonitor`
runs the 6 steps (observe → news → think → risk → execute → reflect) as
plain async function calls. This module wraps each step as an Agno
`Step` and assembles them into a `Workflow`. Two reasons:

  1. Phase 4 (AgentOS): once the Workflow is materialised here, the
     AgentOS scheduler can register it as a cron-triggered runnable
     directly — `POST /schedules` with the workflow id, no APScheduler
     glue. The Workflow object is the seam.

  2. Tracing / sessions: `Workflow.arun(session_id=...)` writes a row
     per cycle to the AgentOS `runs` table including per-step durations
     and outputs, so the dashboard's pipeline panel and the legacy
     `stage_timings` envelope can both consume the same source of truth.

Flag: `settings.agno_workflow_enabled`. When False (default) the
existing `TradingLoopMonitor` is used unchanged. When True, the
composition layer builds a Workflow that wraps the same 6 step callables
the monitor already exposes — same code path, different orchestrator.

NOTE: This file is wiring-only. The actual step callables (observe,
news, think, risk, execute, reflect) are still authored in
`composition.py` / `trading_loop.py`. The Workflow simply replaces the
imperative `await step()` chain with declarative Steps.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

import structlog
from agno.workflow.step import Step
from agno.workflow.workflow import Workflow

if TYPE_CHECKING:
    from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)


# Each step takes the carry-over dict (`session_state`-shaped) and produces
# the next dict. Pragmatic alternative to the `StepInput`/`StepOutput`
# pydantic types Agno ships — keeps this scaffold readable while the full
# typed-context migration lands in Phase 4.
StepFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _step_from_callable(name: str, fn: StepFn) -> Step:
    """Wrap a `(state) -> awaitable[state]` callable as an Agno Step.

    Agno's `Step.executor` accepts a callable; we adapt to its `StepInput`
    by reading from `step_input.message` (the prior step's output) and
    returning a `StepOutput` carrying our updated state under `.content`.
    """

    async def _executor(step_input: Any) -> Any:
        # `step_input.message` is the prior step's `StepOutput.content`.
        # The first step receives the workflow's `input` payload.
        carry = step_input.message if hasattr(step_input, "message") else {}
        if isinstance(carry, dict):
            state = dict(carry)
        else:
            state = {"input": carry}
        next_state = await fn(state)
        # Lazy import — Agno's class is not needed unless we actually run.
        from agno.workflow.types import StepOutput

        return StepOutput(content=next_state)

    return Step(name=name, executor=_executor)


def build_agno_trading_workflow(
    monitor: TradingLoopMonitor,
    settings: Settings,
    *,
    db: Any | None = None,
) -> Workflow:
    """Wrap an existing `TradingLoopMonitor` as an Agno `Workflow`.

    The monitor already owns the 6 step callables. We adapt each into the
    Step shape and chain them. The Workflow's `session_state` is the
    natural place to surface the cycle-wide carry (market snapshot,
    decision, trade list, stage timings).

    Args:
        monitor: The same `TradingLoopMonitor` `composition.build_trading_monitor`
            returns. We read `monitor._observe`, `monitor._news_gather`,
            `monitor._think_fn`, etc. via private attrs — these are stable
            inside the orchestrator's contract.
        settings: Settings instance. Reserved for future use.
        db: Optional Agno DB instance (PostgresDb in Phase 4) for run
            persistence. Pass None until Postgres is wired.
    """
    # Tiny adapters matching the StepFn shape so we can compose declaratively.
    async def _observe(state: dict[str, Any]) -> dict[str, Any]:
        market = await monitor._exchange_observe()
        return {**state, "market": market}

    async def _news(state: dict[str, Any]) -> dict[str, Any]:
        news = await monitor._news_gather()
        return {**state, "news": news}

    async def _think(state: dict[str, Any]) -> dict[str, Any]:
        decision = await monitor._think_fn(state["market"], state.get("news") or [])
        return {**state, "decision": decision}

    async def _risk(state: dict[str, Any]) -> dict[str, Any]:
        # `RiskCheckFn` signature is `(Decision, list[Position]) -> Decision`.
        # The risk step may rewrite the decision (e.g. clamp leverage); we
        # forward the post-check decision into the carry so execute uses it.
        market = state.get("market")
        positions = list(getattr(market, "positions", []) or [])
        post = await monitor._risk_check(state["decision"], positions)
        return {**state, "decision": post, "risk_approved": post is not None}

    async def _execute(state: dict[str, Any]) -> dict[str, Any]:
        if not state.get("risk_approved", True):
            return {**state, "trades": []}
        trades = await monitor._execute_fn(state["decision"])
        return {**state, "trades": trades}

    async def _reflect(state: dict[str, Any]) -> dict[str, Any]:
        decision = state.get("decision")
        if decision is None:
            return state
        await monitor._reflect_fn(decision, state.get("trades") or [])
        return state

    workflow_steps = [
        _step_from_callable("observe", _observe),
        _step_from_callable("news", _news),
        _step_from_callable("think", _think),
        _step_from_callable("risk", _risk),
        _step_from_callable("execute", _execute),
        _step_from_callable("reflect", _reflect),
    ]

    # The Workflow `steps` field accepts a list of mixed primitives (Step,
    # Steps, Loop, Parallel, Condition, Router, Workflow); mypy treats the
    # element type as invariant, so cast to Any to satisfy the annotation
    # without losing the runtime shape.
    workflow = Workflow(
        name="trading-cycle",
        description="OmniTrade 6-step trading cycle (Agno wrapper).",
        steps=cast(Any, workflow_steps),
        db=db,
        session_state={},
    )
    logger.info(
        "trading_workflow_agno.built",
        n_steps=len(workflow_steps),
        has_db=db is not None,
    )
    return workflow


__all__ = ["build_agno_trading_workflow"]
