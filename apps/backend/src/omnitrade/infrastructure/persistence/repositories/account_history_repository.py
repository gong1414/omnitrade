"""AccountHistoryRepository — CRUD for the account_history table."""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import AccountSnapshot
from omnitrade.infrastructure.persistence.models import AccountHistoryORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: AccountHistoryORM) -> AccountSnapshot:
    return AccountSnapshot(
        id=row.id,
        timestamp=row.timestamp,
        total_value=Decimal(str(row.total_value)),
        available_cash=Decimal(str(row.available_cash)),
        unrealized_pnl=Decimal(str(row.unrealized_pnl)),
        realized_pnl=Decimal(str(row.realized_pnl)),
        return_percent=Decimal(str(row.return_percent)),
        sharpe_ratio=Decimal(str(row.sharpe_ratio)) if row.sharpe_ratio is not None else None,
    )


def _domain_to_orm(snap: AccountSnapshot) -> AccountHistoryORM:
    return AccountHistoryORM(
        id=snap.id,
        timestamp=snap.timestamp,
        total_value=float(snap.total_value),
        available_cash=float(snap.available_cash),
        unrealized_pnl=float(snap.unrealized_pnl),
        realized_pnl=float(snap.realized_pnl),
        return_percent=float(snap.return_percent),
        sharpe_ratio=float(snap.sharpe_ratio) if snap.sharpe_ratio is not None else None,
    )


class AccountHistoryRepository:
    """CRUD operations for the account_history table."""

    async def get(self, session: AsyncSession, record_id: int) -> AccountSnapshot | None:
        with_context(logger).debug("account_history_repository.get", record_id=record_id)
        result = await session.get(AccountHistoryORM, record_id)
        return _orm_to_domain(result) if result else None

    async def list_recent(self, session: AsyncSession, limit: int = 100) -> list[AccountSnapshot]:
        with_context(logger).debug("account_history_repository.list_recent", limit=limit)
        stmt = select(AccountHistoryORM).order_by(AccountHistoryORM.timestamp.desc()).limit(limit)
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, snap: AccountSnapshot) -> AccountSnapshot:
        with_context(logger).info("account_history_repository.create")
        row = _domain_to_orm(snap)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)
