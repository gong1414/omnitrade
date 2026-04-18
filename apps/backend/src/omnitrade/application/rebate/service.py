"""RebateService — 24-hour fee-rebate calculator.

Formula:

    total_fees    = SUM(fee) WHERE type='close' AND timestamp >= now - 24h
    rebate_amount = total_fees * rebate_percent / 100

Returns a ``RebateSummary`` value object. Pure enough that the companion
test in ``tests/application/rebate/test_rebate_parity.py`` can feed
synthetic trades and compare to the formula at 1e-9 tolerance.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.rebate.models import RebateSummary, RebateWindow
from omnitrade.domain.services.rebate_calculator import calculate_rebate
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


class RebateService:
    """Computes the rebate summary over a rolling 24-hour window."""

    def __init__(
        self,
        *,
        trade_repo: TradeRepository,
        session_factory: SessionFactory,
        fee_rebate_percent: Decimal = Decimal("20"),
        window_hours: int = 24,
    ) -> None:
        self._trade_repo = trade_repo
        self._session_factory = session_factory
        self._fee_rebate_percent = fee_rebate_percent
        self._window_hours = window_hours

    async def compute_summary(
        self,
        reference_time: datetime | None = None,
    ) -> RebateSummary:
        """Compute the summary anchored at ``reference_time`` (defaults to UTC now)."""
        now = reference_time if reference_time is not None else datetime.now(tz=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = now - timedelta(hours=self._window_hours)

        session = await self._session_factory()
        try:
            trades = await self._trade_repo.list_all(session)
        finally:
            await session.close()

        with_context(logger).info(
            "rebate_service.compute_summary",
            reference_time=now.isoformat(),
            window_hours=self._window_hours,
            trade_count=len(trades),
        )

        total_fees, rebate_amount = calculate_rebate(
            trades,
            fee_rebate_percent=self._fee_rebate_percent,
            window_hours=self._window_hours,
            reference_time=now,
        )
        close_count = 0
        for t in trades:
            if t.type != "close" or t.fee is None:
                continue
            ts = t.timestamp if t.timestamp.tzinfo else t.timestamp.replace(tzinfo=UTC)
            if ts >= cutoff:
                close_count += 1

        return RebateSummary(
            window=RebateWindow(start=cutoff, end=now),
            fee_rebate_percent=self._fee_rebate_percent,
            close_trades_count=close_count,
            total_fees_usdt=total_fees,
            rebate_amount_usdt=rebate_amount,
        )


__all__ = ["RebateService", "SessionFactory"]
