"""AccountRecorderMonitor — persists ``AccountSnapshot`` every tick.

Cadence: ``ACCOUNT_RECORD_INTERVAL_MINUTES`` (default 1 minute).
Delegates to ``AccountService.record_snapshot`` which handles peak,
drawdown, Sharpe, persistence and event emission.
"""

from __future__ import annotations

import structlog

from omnitrade.application.account_service import AccountService
from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class AccountRecorderMonitor:
    """Periodic account-history snapshot recorder."""

    def __init__(
        self,
        *,
        interval_minutes: int,
        account_service: AccountService,
        clock: ClockProtocol | None = None,
    ) -> None:
        self._interval_minutes = interval_minutes
        self._account_service = account_service
        self._clock = clock or SystemClock()

    @property
    def interval_seconds(self) -> float:
        return float(self._interval_minutes * 60)

    async def tick(self) -> None:
        with_context(logger).info("account_recorder_monitor.tick")
        await self._account_service.record_snapshot()


__all__ = ["AccountRecorderMonitor"]
