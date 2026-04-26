"""FastAPI application factory for OmniTrade backend.

Phase 5 scope: mount the full REST + WS surface, wire the ApiContainer
onto ``app.state``, install TraceContext + IPBlacklist middlewares, and
manage the APScheduler lifecycle via the lifespan context.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from omnitrade.api.container import ApiContainer, build_api_container
from omnitrade.api.middleware import IPBlacklistMiddleware
from omnitrade.api.routes import api_router, api_v8_router
from omnitrade.api.sse import sse_router
from omnitrade.config import Settings, get_settings
from omnitrade.observability.log_store import buffer_processor
from omnitrade.observability.trace_context import TraceContextMiddleware, configure_structlog
from omnitrade.observability.tracing import setup_tracing

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

    # T4: install the OpenTelemetry tracing layer before AgentOS wraps the
    # app. Agno's `setup_tracing` is idempotent and AgentOS won't re-register
    # because it sees the already-installed TracerProvider. No-op when
    # `agno_postgres_url` is unset (test path) or `OTEL_TRACING_ENABLED=false`.
    setup_tracing(settings)

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

    # Phase 8.7 / 4.5: compose the trading monitor whenever a configured
    # runtime will invoke it. APScheduler owns the legacy interval path;
    # AgentOS can own just the trading-cycle schedule while leaving
    # SCHEDULER_ENABLED=false.
    app.state.trading_monitor = None
    app.state.invalidation_monitor = None
    app.state.scheduler = None
    has_llm_credentials = _has_llm_credentials(settings)
    if post_container is not None and has_llm_credentials:
        if settings.scheduler_enabled:
            try:
                _start_trading_scheduler(app, settings, post_container)
            except Exception as exc:  # startup wiring is best-effort
                await logger.aerror("omnitrade.scheduler_start_failed", error=str(exc))
        elif settings.agno_scheduler_drives_cycle:
            try:
                _ensure_trading_monitor(app, settings, post_container, driver="agentos")
            except Exception as exc:  # startup wiring is best-effort
                await logger.aerror(
                    "omnitrade.agentos_trading_monitor_build_failed",
                    error=str(exc),
                )

    # Phase 4.5: bind the trading monitor to the AgentOS workflow holder
    # so the registered Workflow can resolve its step callables. Holder is
    # set up in `create_app`; missing in test paths that don't wrap with
    # AgentOS, in which case we silently skip.
    holder = getattr(app.state, "agent_os_monitor_holder", None)
    monitor = getattr(app.state, "trading_monitor", None)
    if holder is not None and monitor is not None:
        holder.set_monitor(monitor)
        logger.info("omnitrade.agent_os_workflow_monitor_bound")

    # Cron / cycle-timeout sanity check (review #7). When the per-cycle
    # timeout exceeds half the schedule interval, two consecutive cycles
    # can overlap and the second one will be rejected by the schedule
    # lock; warn loudly so misconfigurations surface in startup logs.
    if settings.agno_scheduler_drives_cycle:
        interval_s = settings.trading_interval_minutes * 60
        if settings.cycle_trigger_timeout_seconds > interval_s / 2:
            await logger.awarning(
                "omnitrade.cycle_timeout_vs_interval_misconfig",
                cycle_timeout_s=settings.cycle_trigger_timeout_seconds,
                trading_interval_s=interval_s,
                msg=(
                    "cycle_trigger_timeout_seconds > trading_interval/2 — "
                    "consecutive cycles may overlap. Either lengthen "
                    "TRADING_INTERVAL_MINUTES or lower CYCLE_TRIGGER_TIMEOUT_SECONDS."
                ),
            )

    # Phase 4.5 step 2: when AgentOS is configured to drive the trading
    # cycle, register (idempotently) a cron schedule pointing at the
    # `/workflows/trading-cycle/runs` endpoint. **Last** thing in lifespan
    # startup (review #2 — race ordering): only fire after monitor is
    # bound + holder.set_monitor has unblocked any waiting scheduler ticks.
    # Reuse the same `PostgresDb` agent_os_app already opened so we don't
    # leak a parallel connection (review #1).
    shared_db = getattr(app.state, "agent_os_postgres_db", None)
    if (
        settings.agno_postgres_url
        and settings.agno_scheduler_drives_cycle
        and post_container is not None
        and holder is not None
        and getattr(app.state, "trading_monitor", None) is not None
    ):
        try:
            await _register_agentos_trading_schedule(settings, shared_db=shared_db)
        except Exception as exc:  # bootstrap is best-effort
            await logger.aerror(
                "omnitrade.agentos_schedule_register_failed", error=str(exc)
            )

    yield

    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception as exc:  # pragma: no cover — best-effort teardown
            await logger.awarning("omnitrade.scheduler_shutdown_failed", error=str(exc))

    # Reap MCP server subprocesses spawned by the Agno think-fn rather than
    # leaving them to the OS to GC on process exit. The bridge is set on
    # app.state by `_ensure_trading_monitor` when the production think_fn
    # is wired; absent in tests / no-LLM-credentials runs.
    bridge = getattr(app.state, "agno_mcp_bridge", None)
    if bridge is not None:
        try:
            await bridge.close()
        except Exception as exc:  # pragma: no cover — best-effort teardown
            await logger.awarning(
                "omnitrade.agno_mcp_bridge_close_failed", error=str(exc)
            )

    await logger.ainfo("omnitrade.shutdown")


def _has_llm_credentials(settings: Settings) -> bool:
    """Return True when a trading LLM credential is configured."""
    return settings.llm_api_key is not None or settings.deepseek_api_key is not None


def _ensure_trading_monitor(
    app: FastAPI,
    settings: Settings,
    container: ApiContainer,
    *,
    driver: str,
) -> Any:
    """Build and store the trading monitor if startup has not already done so."""
    monitor = getattr(app.state, "trading_monitor", None)
    if monitor is not None:
        return monitor

    from omnitrade.application.composition import build_trading_monitor

    monitor = build_trading_monitor(container, settings)
    app.state.trading_monitor = monitor

    # The Agno think_fn exposes its MCP bridge as an attribute so the
    # lifespan can shut down spawned MCP subprocesses cleanly. Stash the
    # bridge on app.state when present; missing on stub/test think_fns,
    # in which case shutdown becomes a no-op.
    bridge = getattr(getattr(monitor, "_think_fn", None), "mcp_bridge", None)
    if bridge is not None:
        app.state.agno_mcp_bridge = bridge

    logger.info("omnitrade.trading_monitor_built", driver=driver)
    return monitor


def _start_trading_scheduler(
    app: FastAPI,
    settings: Settings,
    container: ApiContainer,
) -> None:
    """Compose + start the APScheduler trading cycle.

    Extracted so the lifespan handler stays small and scheduler-only imports
    stay local (keeps cold-start import graph lean; only pulled when
    SCHEDULER_ENABLED=true).
    """
    from datetime import timedelta

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from omnitrade.application.monitors.account_recorder_monitor import AccountRecorderMonitor
    from omnitrade.application.monitors.invalidation_monitor import InvalidationMonitor
    from omnitrade.application.monitors.partial_profit_monitor import PartialProfitMonitor
    from omnitrade.application.monitors.price_sync_monitor import PriceSyncMonitor
    from omnitrade.application.monitors.stop_loss_monitor import StopLossMonitor
    from omnitrade.application.monitors.trailing_stop_monitor import TrailingStopMonitor
    from omnitrade.infrastructure.llm.agno_llm_adapter import AgnoLLMAdapter

    if not _has_llm_credentials(settings):
        raise RuntimeError("trading scheduler requires an LLM API key")

    # The trading Agent (Agno) owns its own DeepSeek client — this LLMClient
    # is only used by the auxiliary InvalidationMonitor that still consumes
    # the LiteLLM-shaped surface.
    llm = AgnoLLMAdapter.from_settings(settings)
    monitor = _ensure_trading_monitor(app, settings, container, driver="apscheduler")

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
    price_sync_monitor = PriceSyncMonitor(
        interval_seconds=settings.price_sync_interval_seconds,
        exchange=container.exchange,
        position_repo=container.position_repo,
        session_factory=container.open_session,
        event_bus=container.event_bus,
    )

    scheduler = AsyncIOScheduler()
    import datetime as _dt

    # Phase 4.5: when AgentOS scheduler is configured to drive the cycle,
    # the APScheduler trading_cycle job becomes a duplicate runner — skip
    # it so we don't fire two cycles in lock-step. The 6 fast
    # position-protection monitors still run on APScheduler regardless.
    if not settings.agno_scheduler_drives_cycle:
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
    scheduler.add_job(
        price_sync_monitor.tick,
        "interval",
        seconds=settings.price_sync_interval_seconds,
        # Lead with price-sync at +2s so the first stop-loss tick (+5s) and
        # trailing-stop tick (+7s) already see fresh mark prices.
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=2),
        id="price_sync_monitor",
        max_instances=1,
        coalesce=True,
    )

    # Account history recorder — persists snapshots every N minutes.
    # Runs immediately on startup (like nof1.ai) then on interval.
    account_recorder = AccountRecorderMonitor(
        interval_minutes=settings.account_record_interval_minutes,
        account_service=container.account_service,
    )
    scheduler.add_job(
        account_recorder.tick,
        "interval",
        minutes=settings.account_record_interval_minutes,
        next_run_time=_dt.datetime.now(_dt.UTC) + timedelta(seconds=3),
        id="account_recorder",
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


def _cron_for_interval(minutes: int) -> str:
    """Return a cron expression matching the requested cadence.

    * 1..59 minutes → ``*/N * * * *``
    * Whole hours (60, 120, 180, ..., 1380) → ``0 */h * * *``
    * 24 h (1440) → ``0 0 * * *`` (midnight UTC)
    * Anything else (e.g. 90 min) → clamp DOWN to the nearest hour and
      log a warning — the schedule fires later than configured rather
      than earlier, which is the safer side of "wrong".
    """
    if minutes <= 0:
        logger.warning(
            "omnitrade.agentos_schedule_invalid_cadence",
            trading_interval_minutes=minutes,
            fallback="*/20 * * * *",
        )
        return "*/20 * * * *"
    if minutes < 60:
        return f"*/{minutes} * * * *"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"0 */{hours} * * *" if hours < 24 else "0 0 * * *"
    hours = max(1, minutes // 60)
    logger.warning(
        "omnitrade.agentos_schedule_clamped_cadence",
        trading_interval_minutes=minutes,
        cron_hours=hours,
    )
    return f"0 */{hours} * * *"


async def _register_agentos_trading_schedule(
    settings: Settings,
    *,
    shared_db: Any | None = None,
) -> None:
    """Idempotently register the AgentOS cron schedule for the trading
    workflow. The scheduler poller running inside AgentOS picks up the
    row on its next tick and fires the schedule.

    Args:
        settings: The active :class:`Settings`.
        shared_db: Optional pre-built :class:`agno.db.postgres.PostgresDb`
            from :mod:`agent_os_app`. When supplied, the manager reuses
            it — no duplicate Postgres connection is opened. When None
            (defensive path), we open + close our own.

    Schedules persist in Postgres, so re-running the bootstrap with
    ``if_exists='update'`` keeps the cron in sync with config drift
    across restarts.
    """
    from agno.scheduler.manager import ScheduleManager

    cron = _cron_for_interval(settings.trading_interval_minutes)

    own_db = None
    db = shared_db
    if db is None:
        from agno.db.postgres import PostgresDb

        own_db = PostgresDb(db_url=settings.agno_postgres_url)
        db = own_db

    manager = ScheduleManager(db=db)
    try:
        schedule = await manager.acreate(
            name="trading-cycle",
            cron=cron,
            endpoint="/workflows/trading-cycle/runs",
            method="POST",
            description="Trigger the OmniTrade trading cycle on a fixed cadence.",
            payload={"message": "scheduled"},
            timeout_seconds=int(settings.cycle_trigger_timeout_seconds * 4),
            max_retries=0,
            if_exists="update",
        )
        if not schedule.enabled:
            await manager.aenable(schedule.id)

        logger.info(
            "omnitrade.agentos_schedule_registered",
            schedule_id=schedule.id,
            cron=cron,
            endpoint="/workflows/trading-cycle/runs",
        )
    finally:
        # Only close the DB if we opened it. The shared one belongs to
        # AgentOS; AgentOS closes it on app shutdown.
        if own_db is not None:
            close = getattr(own_db, "close", None)
            if callable(close):
                try:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                except Exception as exc:  # pragma: no cover — best-effort teardown
                    logger.warning(
                        "omnitrade.agentos_schedule_db_close_failed",
                        error=str(exc),
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
    app.include_router(sse_router)

    # AgentOS overlays its REST surface (sessions / memory / runs / schedules /
    # workflows) onto the same app. `on_route_conflict='preserve_base_app'`
    # keeps every legacy route live; AgentOS adds its own surface alongside.
    # The trading workflow registers via a MonitorHolder so it can be wired
    # before the lifespan builds the real monitor (see `lifespan` for the
    # late-binding step). Skipped when no LLM credentials are configured.
    if settings.llm_api_key is not None or settings.deepseek_api_key is not None:
        from omnitrade.api.agent_os_app import MonitorHolder, wrap_with_agent_os

        holder = MonitorHolder()
        app.state.agent_os_monitor_holder = holder
        app = wrap_with_agent_os(app, settings, holder)
        # `wrap_with_agent_os` returns a new merged FastAPI app; preserve
        # the holder reference on the merged app's state so the lifespan
        # (which runs against this returned app) can find it.
        app.state.agent_os_monitor_holder = holder

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
