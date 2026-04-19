"""AccountService — computes + persists account snapshots.

Responsibilities:
  * Fetch the raw balance + open positions from the ``ExchangeClient``.
  * Compute derived fields (peak, drawdown, return_percent, sharpe_ratio).
  * Persist the snapshot via ``AccountHistoryRepository``.
  * Emit ``account_update`` events for the WS stream.

The peak is tracked across snapshots using the repository's ``list_recent``;
Phase 5 MVP scans the last 200 rows to compute peak — Phase 6 will add an
indexed materialised column if needed.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.events import EVENT_ACCOUNT_UPDATE, EventBus
from omnitrade.domain.entities import AccountSnapshot
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


def _snapshot_to_dict(snap: AccountSnapshot, *, peak: Decimal, drawdown: Decimal) -> dict[str, Any]:
    return {
        "timestamp": snap.timestamp.isoformat(),
        "total_value": str(snap.total_value),
        "available_cash": str(snap.available_cash),
        "unrealized_pnl": str(snap.unrealized_pnl),
        "realized_pnl": str(snap.realized_pnl),
        "return_percent": str(snap.return_percent),
        "sharpe_ratio": str(snap.sharpe_ratio) if snap.sharpe_ratio is not None else None,
        "peak": str(peak),
        "drawdown_percent": str(drawdown),
    }


class AccountService:
    """Builds + persists + broadcasts ``AccountSnapshot`` rows."""

    def __init__(
        self,
        *,
        exchange: ExchangeClient,
        history_repo: AccountHistoryRepository,
        position_repo: PositionRepository,
        session_factory: SessionFactory,
        event_bus: EventBus,
        initial_balance: Decimal,
        peak_lookback: int = 200,
    ) -> None:
        self._exchange = exchange
        self._history_repo = history_repo
        self._position_repo = position_repo
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._initial_balance = initial_balance
        self._peak_lookback = peak_lookback

    async def _peak_from_history(self, session: AsyncSession) -> Decimal:
        rows = await self._history_repo.list_recent(session, limit=self._peak_lookback)
        if not rows:
            return Decimal(0)
        return max((r.total_value for r in rows), default=Decimal(0))

    @staticmethod
    def _compute_sharpe(total_values: list[Decimal]) -> Decimal | None:
        """Annualised Sharpe from a ``total_value`` time series.

        The earlier implementation averaged *cumulative* return_percent
        rows (which all share the same denominator) so the numerator
        stdev was near-zero and the ratio exploded into absurd values
        (e.g. ``-29405`` with only 2 samples). Use period log-returns
        instead — the same formula the ``/api/stats`` endpoint uses so
        the dashboard shows a single consistent number.

        Returns ``None`` when fewer than two valid samples exist or the
        period-return stdev is zero.
        """
        if len(total_values) < 2:
            return None
        prev: float | None = None
        log_returns: list[float] = []
        for v in total_values:
            cur = float(v)
            if prev is not None and prev > 0 and cur > 0:
                log_returns.append(math.log(cur / prev))
            prev = cur
        if len(log_returns) < 2:
            return None
        mean = sum(log_returns) / len(log_returns)
        var = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
        std = math.sqrt(var)
        if std == 0:
            return None
        annualised = (mean / std) * math.sqrt(252)
        return Decimal(str(annualised))

    async def record_snapshot(self) -> AccountSnapshot:
        """Pull balance + positions, compute peak + drawdown, persist, emit."""
        balance = await self._exchange.fetch_balance()
        positions = await self._exchange.fetch_positions()
        unrealized = sum((p.unrealized_pnl for p in positions), Decimal(0))

        session = await self._session_factory()
        try:
            prior_peak = await self._peak_from_history(session)
            new_peak = max(prior_peak, balance.total_value)
            drawdown = Decimal(0)
            if new_peak > Decimal(0):
                drawdown = ((new_peak - balance.total_value) / new_peak) * Decimal(100)

            # realized_pnl from balance delta (not exchange API which is unreliable).
            # Same pattern as nof1.ai: realizedPnl = totalBalance - initialBalance.
            realized = balance.total_value - self._initial_balance
            return_percent = Decimal(0)
            if self._initial_balance > Decimal(0):
                return_percent = (
                    (balance.total_value - self._initial_balance) / self._initial_balance
                ) * Decimal(100)

            # Sharpe from the ``total_value`` series (period log-returns,
            # annualised) so the AccountCard reads consistent with
            # ``/api/stats.sharpe``.
            recent = await self._history_repo.list_recent(session, limit=self._peak_lookback)
            total_value_series = list(reversed([r.total_value for r in recent])) + [
                balance.total_value
            ]
            sharpe = self._compute_sharpe(total_value_series)

            snap = AccountSnapshot(
                timestamp=datetime.now(tz=UTC),
                total_value=balance.total_value,
                available_cash=balance.available_cash,
                unrealized_pnl=unrealized,
                realized_pnl=realized,
                return_percent=return_percent,
                sharpe_ratio=sharpe,
            )
            persisted = await self._history_repo.create(session, snap)
            await session.commit()
        finally:
            await session.close()

        with_context(logger).info(
            "account_service.record_snapshot",
            total_value=str(persisted.total_value),
            peak=str(new_peak),
            drawdown_percent=str(drawdown),
        )
        await self._event_bus.publish(
            EVENT_ACCOUNT_UPDATE,
            _snapshot_to_dict(persisted, peak=new_peak, drawdown=drawdown),
        )
        return persisted

    async def current_snapshot(self) -> dict[str, Any]:
        """Return the most recent snapshot + peak + drawdown without persisting.

        Used by ``GET /api/v1/account``.
        """
        live = await self._exchange.fetch_balance()
        session = await self._session_factory()
        try:
            recent = await self._history_repo.list_recent(session, limit=self._peak_lookback)
        finally:
            await session.close()

        if not recent:
            # No history yet — derive from the live exchange balance.
            return _snapshot_to_dict(live, peak=live.total_value, drawdown=Decimal(0))

        latest = recent[0]
        peak = max(r.total_value for r in recent)
        drawdown = Decimal(0)
        if peak > Decimal(0):
            drawdown = ((peak - latest.total_value) / peak) * Decimal(100)
        return _snapshot_to_dict(latest, peak=peak, drawdown=drawdown)


__all__ = ["AccountService", "SessionFactory"]
