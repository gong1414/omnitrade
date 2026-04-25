"""AgentOS wrapper for the FastAPI app.

`omnitrade.main.create_app(...)` always overlays AgentOS on top of the
base FastAPI app via `AgentOS(base_app=app, on_route_conflict="preserve_base_app")`.
Legacy `/api/v1/...` and `/ws/stream` routes survive intact while AgentOS
adds its own REST surface (sessions / memory / runs / schedules).

If `settings.agno_postgres_url` is set, an `agno.db.postgres.PostgresDb`
backs AgentOS for session/run persistence. When unset, AgentOS runs
DB-less (in-memory only) so deployments without Postgres still work.

The Workflow + AgentOS native scheduler land in Stage B of the cutover
plan (`/Users/daoyu/.claude/plans/mossy-frolicking-hickey.md`). Today
APScheduler still drives the trading cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)


def _build_status_agent(settings: Settings) -> Any:
    """Return a minimal Agno Agent so AgentOS has at least one registered
    entity. AgentOS refuses to start without agents/teams/workflows/db,
    so this stub gives operators a `/agents/{id}/runs` surface they can
    poke to verify wiring before plugging real agents into the OS.
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


def wrap_with_agent_os(app: FastAPI, settings: Settings) -> FastAPI:
    """Return the merged AgentOS+FastAPI app.

    Args:
        app: The base FastAPI app from `create_app(settings)`.
        settings: The active Settings instance.

    Returns:
        A FastAPI app whose routes are the union of the original routes
        and AgentOS's built-in routes. Path collisions resolve to the
        base app's handler (`on_route_conflict='preserve_base_app'`).
    """
    from agno.os import AgentOS

    db: Any | None = None
    if settings.agno_postgres_url:
        # Imported lazily so projects without Postgres don't pay the
        # psycopg import cost on every cold start.
        from agno.db.postgres import PostgresDb

        db = PostgresDb(db_url=settings.agno_postgres_url)
        logger.info(
            "agent_os_app.postgres_db_attached",
            url_host=settings.agno_postgres_url.split("@", 1)[-1].split("/", 1)[0],
        )

    # AgentOS requires at least one entity to be registered. We always wire
    # a tiny status agent — operator-facing health helper — so the merged
    # app starts even before any trading agents/workflows are registered.
    status_agent = _build_status_agent(settings)

    agent_os = AgentOS(
        name="OmniTrade",
        description="LLM-driven crypto-futures arena · AgentOS shell",
        version="0.1.0",
        agents=[status_agent],
        db=db,
        base_app=app,
        on_route_conflict="preserve_base_app",
    )

    merged: FastAPI = agent_os.get_app()
    logger.info(
        "agent_os_app.wrapped",
        n_routes=len(merged.routes),
        has_db=db is not None,
    )
    return merged


__all__ = ["wrap_with_agent_os"]
