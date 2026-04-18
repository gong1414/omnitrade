"""LessonRepository — CRUD for the trading_lessons table."""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import TradingLesson
from omnitrade.infrastructure.persistence.models import TradingLessonORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: TradingLessonORM) -> TradingLesson:
    return TradingLesson(
        id=row.id,
        pattern=row.pattern,
        action=row.action,
        outcome=row.outcome,
        lesson=row.lesson,
        confidence=Decimal(str(row.confidence)),
        hit_count=row.hit_count,
        market_regime=row.market_regime,
        created_at=row.created_at,
        last_validated=row.last_validated,
        archived=row.archived,
        embedding=None,  # embeddings stored in vector store, not relational DB
    )


def _domain_to_orm(lesson: TradingLesson) -> TradingLessonORM:
    return TradingLessonORM(
        id=lesson.id,
        pattern=lesson.pattern,
        action=lesson.action,
        outcome=lesson.outcome,
        lesson=lesson.lesson,
        confidence=float(lesson.confidence),
        hit_count=lesson.hit_count,
        market_regime=lesson.market_regime,
        created_at=lesson.created_at,
        last_validated=lesson.last_validated,
        archived=lesson.archived,
    )


class LessonRepository:
    """CRUD operations for the trading_lessons table."""

    async def get(self, session: AsyncSession, lesson_id: int) -> TradingLesson | None:
        with_context(logger).debug("lesson_repository.get", lesson_id=lesson_id)
        result = await session.get(TradingLessonORM, lesson_id)
        return _orm_to_domain(result) if result else None

    async def list_active(
        self, session: AsyncSession, regime: str | None = None
    ) -> list[TradingLesson]:
        with_context(logger).debug("lesson_repository.list_active", regime=regime)
        stmt = select(TradingLessonORM).where(TradingLessonORM.archived.is_(False))
        if regime is not None:
            stmt = stmt.where(TradingLessonORM.market_regime == regime)
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, lesson: TradingLesson) -> TradingLesson:
        with_context(logger).info("lesson_repository.create")
        row = _domain_to_orm(lesson)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def archive(self, session: AsyncSession, lesson_id: int) -> None:
        with_context(logger).info("lesson_repository.archive", lesson_id=lesson_id)
        row = await session.get(TradingLessonORM, lesson_id)
        if row is not None:
            row.archived = True
            await session.flush()
