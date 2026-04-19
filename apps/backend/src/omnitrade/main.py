"""FastAPI application factory for OmniTrade backend.

Phase 5 scope: mount the full REST + WS surface, wire the ApiContainer
onto ``app.state``, install TraceContext + IPBlacklist middlewares, and
manage the APScheduler lifecycle via the lifespan context.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from omnitrade.api.container import ApiContainer, build_api_container
from omnitrade.api.middleware import IPBlacklistMiddleware
from omnitrade.api.routes import api_router, api_v8_router
from omnitrade.api.ws import ws_router
from omnitrade.config import Settings, get_settings
from omnitrade.observability.log_store import buffer_processor
from omnitrade.observability.trace_context import TraceContextMiddleware, configure_structlog

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup → yield → shutdown.

    Tests that need an ``ApiContainer`` attach it manually to
    ``app.state.api_container`` before ``httpx.AsyncClient`` dispatches;
    the lifespan only builds the container for real runs (``settings.environment``
    resolved + exchange available). If the startup wiring fails (missing
    credentials in tests) we skip container build so ``/health`` still works.
    """
    settings: Settings = get_settings()
    configure_structlog()

    await logger.ainfo(
        "omnitrade.startup",
        environment=settings.environment,
        strategy=settings.trading_strategy,
        exchange=settings.exchange,
        database_url=settings.database_url,
    )

    # Respect a test-supplied container: only build if none attached.
    if getattr(app.state, "api_container", None) is None:
        try:
            container = _build_runtime_container(settings)
            app.state.api_container = container
        except Exception as exc:  # startup wiring incomplete — log and continue
            await logger.awarning("omnitrade.container_build_failed", error=str(exc))
            app.state.api_container = None

    # Phase 8.3: forward every structlog event into the container's
    # LogBuffer so ``/api/logs`` returns recent events without a log shipper.
    post_container: ApiContainer | None = getattr(app.state, "api_container", None)
    if post_container is not None and getattr(post_container, "log_buffer", None) is not None:
        _install_log_buffer_sidecar(post_container.log_buffer)

    # Phase 8.7: APScheduler-driven trading cycle. Opt-in via
    # ``SCHEDULER_ENABLED=true``; skipped entirely when no LLM key is
    # configured so the API server stays usable in read-only / test modes.
    app.state.trading_monitor = None
    app.state.invalidation_monitor = None
    app.state.scheduler = None
    if (
        post_container is not None
        and settings.scheduler_enabled
        and settings.llm_api_key is not None
    ):
        try:
            _start_trading_scheduler(app, settings, post_container)
        except Exception as exc:  # startup wiring is best-effort
            await logger.aerror("omnitrade.scheduler_start_failed", error=str(exc))

    yield

    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception as exc:  # pragma: no cover — best-effort teardown
            await logger.awarning("omnitrade.scheduler_shutdown_failed", error=str(exc))

    await logger.ainfo("omnitrade.shutdown")


def _start_trading_scheduler(
    app: FastAPI,
    settings: Settings,
    container: ApiContainer,
) -> None:
    """Compose + start the APScheduler trading cycle.

    Extracted so the lifespan handler stays small and ``build_trading_monitor``
    import stays local (keeps cold-start import graph lean; only pulled when
    SCHEDULER_ENABLED=true).
    """
    from datetime import timedelta

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from omnitrade.application.composition import build_trading_monitor
    from omnitrade.application.monitors.invalidation_monitor import InvalidationMonitor
    from omnitrade.application.monitors.partial_profit_monitor import PartialProfitMonitor
    from omnitrade.application.monitors.stop_loss_monitor import StopLossMonitor
    from omnitrade.application.monitors.trailing_stop_monitor import TrailingStopMonitor
    from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient

    assert settings.llm_api_key is not None  # narrowed by caller
    llm = LiteLLMClient(
        model=settings.llm_model_name,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=str(settings.llm_base_url) if settings.llm_base_url else None,
    )
    monitor = build_trading_monitor(container, settings, llm)
    app.state.trading_monitor = monitor

    # PR-D Phase D2: invalidation monitor runs independently of the trading
    # cycle so positions auto-close the moment the LLM-authored
    # invalidation_condition trips, not at the next TRADING_INTERVAL tick.
    invalidation_monitor = InvalidationMonitor(
        interval_seconds=settings.invalidation_check_interval_seconds,
        llm=llm,
        model=settings.llm_model_name,
        exchange=container.exchange,
        multi_tf_fetcher=container.multi_tf_fetcher,
        position_repo=container.position_repo,
        decision_repo=container.decision_repo,
        position_manager=container.position_manager,
        session_factory=container.open_session,
    )
    app.state.invalidation_monitor = invalidation_monitor

    # Position-protection monitors (stop-loss, trailing-stop, partial-profit).
    pos_mon_interval = settings.position_monitor_interval_seconds
    stop_loss_monitor = StopLossMonitor(
        interval_seconds=pos_mon_interval,
        extreme_stop_loss_percent=Decimal(str(settings.extreme_stop_loss_percent)),
        position_repo=container.position_repo,
        session_factory=container.open_session,
        position_manager=container.position_manager,
    )
    trailing_stop_monitor = TrailingStopMonitor(
        interval_seconds=pos_mon_interval,
        position_repo=container.position_repo,
        session_factory=container.open_session,
        position_manager=container.position_manager,
    )
    partial_profit_monitor = PartialProfitMonitor(
        interval_seconds=pos_mon_interval,
        position_repo=container.position_repo,
        session_factory=container.open_session,
        position_manager=container.position_manager,
    )

    scheduler = AsyncIOScheduler()
    import datetime as _dt

    scheduler.add_job(
        monitor.tick,
        "interval",
        minutes=settings.trading_interval_minutes,
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=10),
        id="trading_cycle",
        max_instances=1,  # refuse overlapping runs
        coalesce=True,  # collapse missed ticks into one
    )
    scheduler.add_job(
        invalidation_monitor.tick,
        "interval",
        seconds=settings.invalidation_check_interval_seconds,
        next_run_time=_dt.datetime.now(_dt.UTC)
        + timedelta(seconds=settings.invalidation_check_interval_seconds),
        id="invalidation_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        stop_loss_monitor.tick,
        "interval",
        seconds=pos_mon_interval,
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=5),
        id="stop_loss_monitor",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        trailing_stop_monitor.tick,
        "interval",
        seconds=pos_mon_interval,
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=7),
        id="trailing_stop_monitor",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        partial_profit_monitor.tick,
        "interval",
        seconds=pos_mon_interval,
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=8),
        id="partial_profit_monitor",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    # Structlog sync emit — lifespan callers use ``ainfo``; this helper is
    # sync so we use the regular logger call.
    logger.info(
        "omnitrade.scheduler_started",
        interval_minutes=settings.trading_interval_minutes,
    )


def _install_log_buffer_sidecar(log_buffer: Any) -> None:
    """Re-configure structlog so events are mirrored into ``log_buffer``.

    Phase 8.3: ``configure_structlog()`` runs first with the JSON renderer;
    we reinstall the same processor chain with ``buffer_processor`` inserted
    just before the renderer. Idempotent — calling twice is harmless, the
    replacement happens in-place.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            # Match trace_context.configure_structlog() order:
            _add_correlation_id_passthrough(),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            buffer_processor(log_buffer),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _add_correlation_id_passthrough() -> Any:
    """Import and return the add_correlation_id processor lazily.

    Kept out of the module-level imports so tests that stub ``trace_context``
    do not fight a cached reference.
    """
    from omnitrade.observability.trace_context import add_correlation_id

    return add_correlation_id


def _build_runtime_container(settings: Settings) -> ApiContainer:
    """Construct the production ``ApiContainer`` + wire infrastructure.

    Extracted so tests can patch this function to inject a fake exchange
    without touching the lifespan handler.
    """
    from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange
    from omnitrade.infrastructure.persistence.database import build_engines, init_async_factory

    _sync_eng, _sync_fact, _async_eng, async_factory = build_engines(settings.database_url)
    init_async_factory(async_factory)

    if settings.exchange == "gate":
        api_key = settings.gate_api_key.get_secret_value() if settings.gate_api_key else ""
        api_secret = settings.gate_api_secret.get_secret_value() if settings.gate_api_secret else ""
        exchange = CCXTExchange(
            exchange_id="gate",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.gate_use_testnet,
        )
    else:
        api_key = settings.okx_api_key.get_secret_value() if settings.okx_api_key else ""
        api_secret = settings.okx_api_secret.get_secret_value() if settings.okx_api_secret else ""
        passphrase = (
            settings.okx_api_passphrase.get_secret_value() if settings.okx_api_passphrase else None
        )
        exchange = CCXTExchange(
            exchange_id="okx",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.okx_use_testnet,
            passphrase=passphrase,
        )
    return build_api_container(
        settings=settings,
        exchange=exchange,
        session_factory=async_factory,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="OmniTrade",
        version="0.1.0",
        description="AI Trading Agent Platform — Python 3.11 backend",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware (outer → inner) ─────────────────────────────────────── #
    # CORS must be outermost so preflight OPTIONS responses carry the
    # Access-Control-Allow-* headers before any other middleware runs.
    # Permissive default for local/testnet dev; tighten via reverse proxy
    # in production (nginx / cloudflare).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://frontend:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # IP blacklist runs after CORS so browser preflight is never blocked.
    app.add_middleware(IPBlacklistMiddleware)
    app.add_middleware(TraceContextMiddleware)

    # ── Routes ─────────────────────────────────────────────────────────── #
    @app.get("/health", tags=["platform"])
    async def health() -> dict[str, Any]:
        """Liveness probe — returns 200 when the process is alive."""
        import datetime

        return {
            "ok": True,
            "time": datetime.datetime.now(datetime.UTC).isoformat(),
            "environment": settings.environment,
            "version": "0.1.0",
        }

    app.include_router(api_router)
    app.include_router(api_v8_router)
    app.include_router(ws_router)

    return app


def main() -> None:
    """Entry point for `omnitrade` CLI script (uv run omnitrade)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "omnitrade.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=settings.platform_port,
        reload=False,
        log_config=None,  # structlog handles logging
    )


if __name__ == "__main__":
    main()
