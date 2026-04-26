"""OpenTelemetry tracing overlay (T4).

OmniTrade already emits structlog events with a correlation-id processor
(:mod:`omnitrade.observability.trace_context`). T4 adds a parallel OTel
span layer so AgentOS's ``GET /traces`` endpoint surfaces one span per
Agno cycle and one per tool call without disturbing existing
``with_context(logger).info(...)`` call sites.

Implementation note
-------------------

Agno 2.x ships its own tracing helper: :func:`agno.tracing.setup_tracing`
(see ``agno/tracing/setup.py`` and ``agno/os/utils.py::setup_tracing_for_os``).
That helper:

  1. Creates a :class:`opentelemetry.sdk.trace.TracerProvider`.
  2. Attaches Agno's :class:`agno.tracing.exporter.DatabaseSpanExporter`
     (writes spans into the ``traces`` + ``spans`` tables of the same
     Postgres DB AgentOS already uses for sessions/memory/runs).
  3. Calls :class:`openinference.instrumentation.agno.AgnoInstrumentor`
     so every ``Agent.run`` / ``Model.response`` / tool call emits a
     span automatically.

We invoke it directly from the FastAPI lifespan **before** the AgentOS
overlay wraps the app. Agno's helper is itself idempotent (it bails when
:func:`opentelemetry.trace.get_tracer_provider` already returns a real
``TracerProvider``), and we add a module-level ``_INITIALIZED`` flag as a
belt-and-suspenders guard for testbeds that swap providers under us.

When ``settings.agno_postgres_url`` is unset (test path, DB-less local
dev) :func:`setup_tracing` is a no-op — there is nowhere to persist spans
and AgentOS's ``/traces`` route would 404 anyway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)

# Module-level flag — guards against double-registration across reload
# cycles, repeated test fixtures, and the AgentOS auto-wire path which
# may also call its own ``setup_tracing_for_os`` after us.
_INITIALIZED: bool = False


def setup_tracing(settings: Settings) -> None:
    """Wire Agno's OTel tracing layer onto the same Postgres DB AgentOS uses.

    No-op when:
      * ``settings.agno_postgres_url`` is None (DB-less / test path).
      * ``settings.otel_tracing_enabled`` is False (kill switch).
      * This function has already run successfully in this process.
      * The underlying Agno / OpenTelemetry imports fail
        (logged at warning level — the cycle still runs).

    On success spans are persisted into Postgres ``traces`` + ``spans``
    tables and surface via AgentOS routes:

      * ``GET /traces`` — paginated trace summaries
      * ``GET /traces/{trace_id}`` — full hierarchical span tree
      * ``POST /traces/search`` — structured search by run/session/etc.

    Idempotency is enforced two ways:
      1. Module-level ``_INITIALIZED`` flag (this function).
      2. Agno's own ``setup_tracing`` checks the global tracer provider
         and bails if a real ``TracerProvider`` is already installed.
    """
    global _INITIALIZED

    if _INITIALIZED:
        logger.debug("tracing.setup.skip", reason="already_initialized")
        return

    if not settings.otel_tracing_enabled:
        logger.info("tracing.setup.skip", reason="otel_tracing_enabled=false")
        return

    if not settings.agno_postgres_url:
        # Test / DB-less path — Agno's DatabaseSpanExporter requires a
        # real DB; without one there is nothing to export to.
        logger.info("tracing.setup.skip", reason="agno_postgres_url unset")
        return

    try:
        from agno.db.postgres import PostgresDb
        from agno.tracing import setup_tracing as agno_setup_tracing
    except ImportError as exc:
        # Either Agno itself is missing (shouldn't happen — it's a hard
        # dep) or the OTel SDK / openinference shim isn't installed. In
        # the latter case Agno's own helper would have logged an
        # ImportError downstream; we surface it earlier here so the
        # operator sees a single root-cause line.
        logger.warning(
            "tracing.setup.import_failed",
            error=str(exc),
            hint=(
                "install opentelemetry-sdk + openinference-instrumentation-agno "
                "(pinned in apps/backend/pyproject.toml)"
            ),
        )
        return

    try:
        db = PostgresDb(db_url=settings.agno_postgres_url)
        # SimpleSpanProcessor (Agno default: ``batch_processing=False``)
        # writes spans synchronously on flush — fine for our cadence
        # (cycles are 20 minutes, tool calls << 1k/cycle) and means a
        # crash mid-cycle still persists every span emitted so far.
        agno_setup_tracing(db=db)
    except Exception as exc:  # pragma: no cover — best-effort wiring
        logger.warning("tracing.setup.failed", error=str(exc))
        return

    _INITIALIZED = True
    logger.info(
        "tracing.setup",
        backend="agno.tracing.setup_tracing",
        db="postgres",
        host=settings.agno_postgres_url.split("@", 1)[-1].split("/", 1)[0],
    )


def reset_for_tests() -> None:
    """Reset the module-level guard so tests can re-exercise the no-op paths.

    Production code never calls this — only the unit tests in
    ``tests/observability/test_tracing.py`` toggle it between cases.
    """
    global _INITIALIZED
    _INITIALIZED = False


__all__ = ["reset_for_tests", "setup_tracing"]
