"""OutcomeRepository — CRUD for the trade_outcomes table."""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import TradeOutcome
from omnitrade.infrastructure.persistence.models import TradeOutcomeORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: TradeOutcomeORM) -> TradeOutcome:
    return TradeOutcome(
        id=row.id,
        trade_id=row.trade_id,
        symbol=row.symbol,
        side=row.side,
        entry_conditions_json=row.entry_conditions_json,
        exit_conditions_json=row.exit_conditions_json,
        pnl_percent=Decimal(str(row.pnl_percent)) if row.pnl_percent is not None else None,
        duration_hours=(
            Decimal(str(row.duration_hours)) if row.duration_hours is not None else None
        ),
        lesson_extracted=row.lesson_extracted,
        created_at=row.created_at,
    )


def _domain_to_orm(outcome: TradeOutcome) -> TradeOutcomeORM:
    return TradeOutcomeORM(
        id=outcome.id,
        trade_id=outcome.trade_id,
        symbol=outcome.symbol,
        side=outcome.side,
        entry_conditions_json=outcome.entry_conditions_json,
        exit_conditions_json=outcome.exit_conditions_json,
        pnl_percent=float(outcome.pnl_percent) if outcome.pnl_percent is not None else None,
        duration_hours=(
            float(outcome.duration_hours) if outcome.duration_hours is not None else None
        ),
        lesson_extracted=outcome.lesson_extracted,
        created_at=outcome.created_at,
    )


class OutcomeRepository:
    """CRUD operations for the trade_outcomes table."""

    async def get(self, session: AsyncSession, outcome_id: int) -> TradeOutcome | None:
        with_context(logger).debug("outcome_repository.get", outcome_id=outcome_id)
        result = await session.get(TradeOutcomeORM, outcome_id)
        return _orm_to_domain(result) if result else None

    async def list_unextracted(self, session: AsyncSession) -> list[TradeOutcome]:
        with_context(logger).debug("outcome_repository.list_unextracted")
        stmt = select(TradeOutcomeORM).where(TradeOutcomeORM.lesson_extracted.is_(False))
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, outcome: TradeOutcome) -> TradeOutcome:
        with_context(logger).info("outcome_repository.create", symbol=outcome.symbol)
        row = _domain_to_orm(outcome)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def mark_extracted(self, session: AsyncSession, outcome_id: int) -> None:
        with_context(logger).info("outcome_repository.mark_extracted", outcome_id=outcome_id)
        row = await session.get(TradeOutcomeORM, outcome_id)
        if row is not None:
            row.lesson_extracted = True
            await session.flush()
