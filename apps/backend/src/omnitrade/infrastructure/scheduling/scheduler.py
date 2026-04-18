"""OmniScheduler — APScheduler wrapper wiring all 5 trading loops.

All 5 loops (consensus plan §7 R1 — none folded):
  1. trading_loop          — every trading_interval_minutes (default 20 min)
  2. trailing_stop_loop    — every 10 seconds
  3. partial_profit_loop   — every 10 seconds
  4. account_recorder_loop — every account_record_interval_minutes (default 1 min)
  5. news_fetch_loop       — every 5 minutes

Each loop is a stub that logs with TraceContext and returns.
Phase 4/5 will fill in the actual work by replacing the stubs via loop_registry.

Graceful shutdown via stop() — waits for running jobs to finish.
"""

from __future__ import annotations

from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from omnitrade.infrastructure.scheduling import loop_registry
from omnitrade.infrastructure.scheduling.loop_registry import LoopSpec
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


# ── Stub loop functions ────────────────────────────────────────────────────


async def _trading_loop_stub() -> None:
    """Stub: main AI trading loop. Phase 4/5 replaces with real implementation."""
    with_context(logger).info("scheduler.trading_loop.tick")


async def _trailing_stop_loop_stub() -> None:
    """Stub: trailing-stop monitor. Phase 5 replaces with real implementation."""
    with_context(logger).info("scheduler.trailing_stop_loop.tick")


async def _partial_profit_loop_stub() -> None:
    """Stub: partial-profit monitor (NOT folded — consensus §7 R1).

    Phase 5 replaces with the partial-profit three-way-state monitor.
    """
    with_context(logger).info("scheduler.partial_profit_loop.tick")


async def _account_recorder_loop_stub() -> None:
    """Stub: account-history recorder. Phase 5 replaces with real implementation."""
    with_context(logger).info("scheduler.account_recorder_loop.tick")


async def _news_fetch_loop_stub() -> None:
    """Stub: news-fetch loop. Phase 5 replaces with real implementation."""
    with_context(logger).info("scheduler.news_fetch_loop.tick")


# ── OmniScheduler ─────────────────────────────────────────────────────────


class OmniScheduler:
    """APScheduler wrapper that registers and manages all 5 trading loops.

    Args:
        trading_interval_minutes: Main loop interval (default 20).
        account_record_interval_minutes: Account recorder interval (default 1).
        timezone: Scheduler timezone string (default "UTC").
    """

    def __init__(
        self,
        trading_interval_minutes: int = 20,
        account_record_interval_minutes: int = 1,
        timezone: str = "UTC",
    ) -> None:
        self._trading_interval_minutes = trading_interval_minutes
        self._account_record_interval_minutes = account_record_interval_minutes
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._specs: list[LoopSpec] = []

    def _build_specs(self) -> list[LoopSpec]:
        """Build all 5 LoopSpec instances from configuration."""
        return [
            LoopSpec(
                name="trading_loop",
                interval_seconds=self._trading_interval_minutes * 60,
                callable=_trading_loop_stub,
                description="Main AI trading loop",
            ),
            LoopSpec(
                name="trailing_stop_loop",
                interval_seconds=10,
                callable=_trailing_stop_loop_stub,
                description="Trailing-stop position monitor",
            ),
            LoopSpec(
                name="partial_profit_loop",
                interval_seconds=10,
                callable=_partial_profit_loop_stub,
                description="Partial-profit position monitor (NOT folded)",
            ),
            LoopSpec(
                name="account_recorder_loop",
                interval_seconds=self._account_record_interval_minutes * 60,
                callable=_account_recorder_loop_stub,
                description="Periodic account-history snapshot recorder",
            ),
            LoopSpec(
                name="news_fetch_loop",
                interval_seconds=5 * 60,  # 5 minutes per upstream scheduledNewsService.ts
                callable=_news_fetch_loop_stub,
                description="News-fetch loop (upstream: scheduledNewsService.ts)",
            ),
        ]

    def start(self) -> None:
        """Register all 5 jobs and start the scheduler."""
        self._specs = self._build_specs()
        for spec in self._specs:
            loop_registry.register(spec)
            self._scheduler.add_job(
                spec.callable,
                trigger=IntervalTrigger(seconds=spec.interval_seconds),
                id=spec.name,
                name=spec.description,
                replace_existing=True,
                max_instances=1,
            )
            with_context(logger).info(
                "scheduler.job_registered",
                job_id=spec.name,
                interval_seconds=spec.interval_seconds,
            )
        self._scheduler.start()
        with_context(logger).info(
            "scheduler.started",
            job_count=len(self._specs),
        )

    def stop(self, wait: bool = True) -> None:
        """Gracefully stop the scheduler.

        Args:
            wait: If True, wait for currently running jobs to finish.
        """
        with_context(logger).info("scheduler.stopping", wait=wait)
        self._scheduler.shutdown(wait=wait)
        with_context(logger).info("scheduler.stopped")

    def get_jobs(self) -> list[dict[str, Any]]:
        """Return a list of registered job metadata for introspection."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]

    def replace_loop(
        self,
        name: str,
        new_callable: Any,
        interval_seconds: float | None = None,
    ) -> None:
        """Replace a loop stub with a real implementation (used by Phase 5).

        Args:
            name: Job ID to replace.
            new_callable: New async callable.
            interval_seconds: New interval; None = keep existing.
        """
        existing = loop_registry.get(name)
        if existing is None:
            raise ValueError(f"Loop {name!r} not found in registry")
        new_interval = (
            interval_seconds if interval_seconds is not None else existing.interval_seconds
        )
        new_spec = LoopSpec(
            name=name,
            interval_seconds=new_interval,
            callable=new_callable,
            description=existing.description,
        )
        loop_registry.register(new_spec)
        self._scheduler.modify_job(
            name,
            trigger=IntervalTrigger(seconds=new_interval),
            func=new_callable,
        )
        with_context(logger).info(
            "scheduler.loop_replaced",
            name=name,
            interval_seconds=new_interval,
        )

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is currently running."""
        return bool(self._scheduler.running)
