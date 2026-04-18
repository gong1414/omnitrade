"""DecisionRepository — CRUD for the agent_decisions table."""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import AgentDecision
from omnitrade.infrastructure.persistence.models import AgentDecisionORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: AgentDecisionORM) -> AgentDecision:
    return AgentDecision(
        id=row.id,
        timestamp=row.timestamp,
        iteration=row.iteration,
        market_analysis=row.market_analysis,
        decision=row.decision,
        actions_taken=row.actions_taken,
        account_value=Decimal(str(row.account_value)),
        positions_count=row.positions_count,
    )


def _domain_to_orm(dec: AgentDecision) -> AgentDecisionORM:
    return AgentDecisionORM(
        id=dec.id,
        timestamp=dec.timestamp,
        iteration=dec.iteration,
        market_analysis=dec.market_analysis,
        decision=dec.decision,
        actions_taken=dec.actions_taken,
        account_value=float(dec.account_value),
        positions_count=dec.positions_count,
    )


class DecisionRepository:
    """CRUD operations for the agent_decisions table."""

    async def get(self, session: AsyncSession, decision_id: int) -> AgentDecision | None:
        with_context(logger).debug("decision_repository.get", decision_id=decision_id)
        result = await session.get(AgentDecisionORM, decision_id)
        return _orm_to_domain(result) if result else None

    async def list_recent(self, session: AsyncSession, limit: int = 50) -> list[AgentDecision]:
        with_context(logger).debug("decision_repository.list_recent", limit=limit)
        stmt = select(AgentDecisionORM).order_by(AgentDecisionORM.timestamp.desc()).limit(limit)
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, dec: AgentDecision) -> AgentDecision:
        with_context(logger).info("decision_repository.create", iteration=dec.iteration)
        row = _domain_to_orm(dec)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)
