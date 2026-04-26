"""Agno Workflow wrapper around :class:`TradingLoopMonitor.tick`.

Wraps the production trading-cycle tick as a single-step Agno
``Workflow``. Two reasons:

  1. **AgentOS visibility.** Once registered with
     ``AgentOS(workflows=[wf])``, operators can trigger it via
     ``POST /workflows/{id}/runs`` and inspect run history under
     ``GET /workflows/{id}/runs``. Each invocation lands as a row in
     the AgentOS workflow-runs table when Postgres is wired.

  2. **Late binding.** AgentOS overlay is built in
     :func:`omnitrade.main.create_app` before FastAPI lifespan runs, so
     the trading monitor doesn't exist yet. The factory takes a
     ``monitor_accessor`` callable instead of the monitor itself; the
     lifespan populates the accessor's source after building the
     ``ApiContainer``.

Why a single step rather than 6
-------------------------------
Earlier revisions exposed each pipeline phase (observe / news / think /
risk / execute / reflect) as a separate ``Step``. Splitting them
required passing :class:`MarketSnapshot` / :class:`Decision` between
steps via Agno's ``StepOutput.content`` dict. That dict is JSON-encoded
when the workflow session is persisted, and Pydantic models with
``Decimal`` fields are not directly JSON-serialisable, so AgentOS
swallowed every run with an "Object of type MarketSnapshot is not JSON
serializable" warning. Collapsing to a single step that calls
``monitor.tick()`` (i.e. the production cycle entry point) sidesteps
the issue: the workflow still gets logged, but the carry is just an
"ok" sentinel. Per-phase tracing is still available through structlog
correlation ids — the visibility loss is cosmetic.
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


MonitorAccessor = Callable[[], "TradingLoopMonitor | None"]
"""Returns the live monitor, or None if the FastAPI lifespan hasn't
populated it yet. The workflow's tick step calls this on every run so
binding the monitor late (after AgentOS has already taken a reference
to the workflow) still works."""


def build_agno_trading_workflow(
    monitor_accessor: MonitorAccessor,
    settings: Settings,
    *,
    db: Any | None = None,
) -> Workflow:
    """Construct an Agno ``Workflow`` whose single step drives the cycle.

    Args:
        monitor_accessor: Zero-arg callable returning the current
            ``TradingLoopMonitor`` (or ``None`` if startup hasn't built
            it yet). Each cycle resolves it freshly so the workflow
            survives container rebuilds in tests.
        settings: Settings instance. Reserved for future use.
        db: Optional Agno DB instance (PostgresDb) for run persistence.
    """

    async def _tick_executor(step_input: Any) -> Any:
        from agno.workflow.types import StepOutput

        monitor = monitor_accessor()
        if monitor is None:
            return StepOutput(
                content={
                    "status": "skipped",
                    "reason": "trading_workflow: monitor not initialized — "
                    "FastAPI lifespan hasn't built ApiContainer yet",
                },
                success=False,
                error="monitor_unavailable",
            )

        try:
            await monitor.tick()
        except Exception as exc:  # pragma: no cover — surfaced to operator
            logger.error("trading_workflow.tick_failed", error=str(exc))
            return StepOutput(
                content={"status": "error", "error": str(exc)},
                success=False,
                error=str(exc),
            )

        # The cycle is entirely side-effect — DecisionService records the
        # decision row, EventBus publishes the WS frames. The workflow's
        # carry is just an "ok" so the AgentOS run history shows a clean
        # status string.
        return StepOutput(content={"status": "ok"})

    tick_step = Step(name="tick", executor=_tick_executor)

    workflow = Workflow(
        name="trading-cycle",
        description=(
            "OmniTrade trading cycle (observe → news → think → risk → "
            "execute → reflect, wrapped as a single Agno workflow step)."
        ),
        steps=cast(Any, [tick_step]),
        db=db,
    )
    logger.info(
        "trading_workflow.built",
        n_steps=1,
        has_db=db is not None,
    )
    return workflow


__all__ = ["MonitorAccessor", "build_agno_trading_workflow"]
