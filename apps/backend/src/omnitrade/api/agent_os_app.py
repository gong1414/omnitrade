"""AgentOS overlay for the FastAPI app (Phase 4 + 4.5).

:func:`omnitrade.main.create_app` overlays AgentOS on top of the base
FastAPI app via ``AgentOS(base_app=app, on_route_conflict='preserve_base_app')``.
Legacy ``/api/v1/...`` and ``/sse/stream`` routes survive intact while
AgentOS adds its own REST surface (sessions / memory / runs / schedules /
workflows).

Phase 4.5 (this revision) registers the trading ``Workflow`` with
AgentOS via a ``MonitorHolder`` — the monitor itself doesn't exist
until the lifespan handler runs, so the workflow's step closures
read it from the holder on every cycle. AgentOS's cron scheduler is
also enabled when ``settings.agno_postgres_url`` is set; schedules are
managed via ``POST /schedules`` at runtime (see
``docs/AGNO_MIGRATION_TRACKER.md`` for the bootstrap recipe).

The placeholder "omnitrade-status" agent stays — AgentOS still requires
at least one entity registered, and an operator-facing read-only Q&A
agent is a nice surface to keep around.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

    from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)


class MonitorHolder:
    """Late-bound reference to the trading monitor.

    AgentOS captures the trading workflow object at :func:`create_app`
    time, but the monitor is only constructed inside the FastAPI
    lifespan handler (after the ``ApiContainer`` is built). The holder
    closes the gap: the workflow's step closures resolve
    :meth:`get_monitor` on every cycle, so populating it from the
    lifespan is enough to make the workflow runnable.

    Threading model
    ---------------
    Write-once at lifespan startup, read many times during request
    handling. Both write (``set_monitor``) and read (``get_monitor``)
    are guarded with an :class:`asyncio.Event` so an early schedule
    fire that beats lifespan startup waits politely instead of seeing
    ``None``.
    """

    def __init__(self) -> None:
        self._monitor: TradingLoopMonitor | None = None
        # Event is created lazily — :class:`MonitorHolder` is constructed
        # inside ``create_app`` which may run on a thread that doesn't
        # own the eventual asyncio loop yet. The event is only ever
        # touched from inside the loop later (lifespan + request paths),
        # so deferring construction is safe.
        self._ready_event: Any | None = None

    def _event(self) -> Any:
        if self._ready_event is None:
            import asyncio

            self._ready_event = asyncio.Event()
        return self._ready_event

    def set_monitor(self, monitor: TradingLoopMonitor) -> None:
        """Bind the live monitor. Must be called once, from the lifespan."""
        if self._monitor is not None:
            logger.warning(
                "monitor_holder.rebind_attempt",
                msg="set_monitor called twice; ignoring later call.",
            )
            return
        self._monitor = monitor
        self._event().set()

    def get_monitor(self) -> TradingLoopMonitor:
        """Return the bound monitor or raise ``RuntimeError``.

        Synchronous accessor used inside the workflow's tick step —
        lifespan startup must complete before the AgentOS scheduler
        can fire (the scheduler poller runs on the same loop, and
        FastAPI doesn't accept requests until lifespan finishes).
        """
        if self._monitor is None:
            raise RuntimeError(
                "monitor_holder: trading monitor not yet bound — "
                "FastAPI lifespan startup hasn't completed"
            )
        return self._monitor

    async def aget_monitor(self, timeout: float = 30.0) -> TradingLoopMonitor:
        """Async variant: waits up to ``timeout`` for the monitor to bind."""
        if self._monitor is not None:
            return self._monitor
        import asyncio

        try:
            await asyncio.wait_for(self._event().wait(), timeout=timeout)
        except TimeoutError as exc:
            raise RuntimeError(
                f"monitor_holder: monitor not bound after {timeout}s "
                "— lifespan startup may have failed"
            ) from exc
        return self.get_monitor()


def _build_status_agent(settings: Settings) -> Any:
    """Operator-facing read-only Q&A agent.

    AgentOS requires at least one entity (agent / team / workflow / db)
    to start; the trading workflow is the load-bearing entity, but a
    tiny status agent stays around so operators have a low-stakes
    surface to poke at /agents/* before invoking the workflow.
    """
    from agno.agent import Agent
    from agno.models.deepseek import DeepSeek

    api_key: str | None = None
    if settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value()
    elif settings.deepseek_api_key is not None:
        api_key = settings.deepseek_api_key.get_secret_value()
    base_url = str(settings.llm_base_url) if settings.llm_base_url is not None else None
    model_id = settings.agno_llm_model.split("/", 1)[-1]

    model_kwargs: dict[str, Any] = {"id": model_id}
    if api_key:
        model_kwargs["api_key"] = api_key
    if base_url:
        model_kwargs["base_url"] = base_url

    return Agent(
        name="omnitrade-status",
        description="Status / health Q&A agent for OmniTrade operators.",
        instructions=(
            "You are a read-only operator helper. Answer brief questions "
            "about OmniTrade's trading state. You have no tools; if a "
            "question requires data fetching, say so plainly."
        ),
        model=DeepSeek(**model_kwargs),
        markdown=False,
        telemetry=False,
    )


def wrap_with_agent_os(
    app: FastAPI,
    settings: Settings,
    holder: MonitorHolder,
) -> FastAPI:
    """Return the merged AgentOS+FastAPI app.

    Args:
        app: The base FastAPI app from ``create_app(settings)``.
        settings: The active Settings instance.
        holder: A :class:`MonitorHolder` whose ``monitor`` is populated
            by the FastAPI lifespan once the ``ApiContainer`` exists.
            The trading workflow's step callables read from this on
            every run.

    Returns:
        A FastAPI app whose routes are the union of the original routes
        and AgentOS's built-in routes. Path collisions resolve to the
        base app's handler (``on_route_conflict='preserve_base_app'``).
    """
    from agno.os import AgentOS

    from omnitrade.application.trading_workflow import build_agno_trading_workflow

    db: Any | None = None
    if settings.agno_postgres_url:
        from agno.db.postgres import PostgresDb

        db = PostgresDb(db_url=settings.agno_postgres_url)
        logger.info(
            "agent_os_app.postgres_db_attached",
            url_host=settings.agno_postgres_url.split("@", 1)[-1].split("/", 1)[0],
        )
        # Stash the same DB on the FastAPI app so the lifespan handler can
        # reuse it for schedule registration without opening a second
        # Postgres connection (review issue #1: connection leak).
        app.state.agent_os_postgres_db = db

    status_agent = _build_status_agent(settings)
    workflow = build_agno_trading_workflow(
        lambda: holder.monitor,
        settings,
        db=db,
    )

    # AgentOS native scheduler: enabled only when Postgres is available
    # (the scheduler persists schedules to the same DB). Without it,
    # /schedules would 500 the moment a cron tick fires.
    scheduler_enabled = db is not None

    scheduler_kwargs: dict[str, Any] = {}
    if scheduler_enabled:
        if settings.agno_scheduler_token is not None:
            scheduler_kwargs["internal_service_token"] = (
                settings.agno_scheduler_token.get_secret_value()
            )
        scheduler_kwargs["scheduler_base_url"] = settings.agno_scheduler_base_url
        scheduler_kwargs["scheduler_poll_interval"] = settings.agno_scheduler_poll_interval

    agent_os = AgentOS(
        name="OmniTrade",
        description="LLM-driven crypto-futures arena · AgentOS shell",
        version="0.1.0",
        agents=[status_agent],
        workflows=[workflow],
        db=db,
        base_app=app,
        on_route_conflict="preserve_base_app",
        scheduler=scheduler_enabled,
        telemetry=False,
        **scheduler_kwargs,
    )

    merged: FastAPI = agent_os.get_app()
    logger.info(
        "agent_os_app.wrapped",
        n_routes=len(merged.routes),
        has_db=db is not None,
        scheduler_enabled=scheduler_enabled,
        n_workflows=1,
    )
    return merged


__all__ = ["MonitorHolder", "wrap_with_agent_os"]
