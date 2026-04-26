"""DecisionRepository — CRUD for the agent_decisions table."""

from __future__ import annotations

import json
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import AgentDecision
from omnitrade.infrastructure.persistence.models import AgentDecisionORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: AgentDecisionORM) -> AgentDecision:
    # gates_passed and plan are stored as JSON strings; None for legacy rows.
    gates_passed = json.loads(row.gates_passed) if row.gates_passed is not None else None
    plan = json.loads(row.plan) if row.plan is not None else None
    return AgentDecision(
        id=row.id,
        timestamp=row.timestamp,
        iteration=row.iteration,
        market_analysis=row.market_analysis,
        decision=row.decision,
        actions_taken=row.actions_taken,
        account_value=Decimal(str(row.account_value)),
        positions_count=row.positions_count,
        symbol=row.symbol,
        side=row.side,
        run_id=row.run_id or "",
        # StructuredReason fields — DB column ``confidence`` → domain ``structured_confidence``
        market_context=row.market_context,
        gates_passed=gates_passed,
        invalidation_condition=row.invalidation_condition,
        plan=plan,
        structured_confidence=row.confidence,
        output_language=row.output_language,
        justification=row.justification,
    )


def _domain_to_orm(dec: AgentDecision) -> AgentDecisionORM:
    # gates_passed and plan are serialised to JSON strings for TEXT columns.
    gates_passed_json = json.dumps(dec.gates_passed) if dec.gates_passed is not None else None
    plan_json = json.dumps(dec.plan) if dec.plan is not None else None
    return AgentDecisionORM(
        id=dec.id,
        timestamp=dec.timestamp,
        iteration=dec.iteration,
        market_analysis=dec.market_analysis,
        decision=dec.decision,
        actions_taken=dec.actions_taken,
        account_value=float(dec.account_value),
        positions_count=dec.positions_count,
        symbol=dec.symbol,
        side=dec.side,
        run_id=dec.run_id,
        # StructuredReason fields — domain ``structured_confidence`` → DB column ``confidence``
        market_context=dec.market_context,
        gates_passed=gates_passed_json,
        invalidation_condition=dec.invalidation_condition,
        plan=plan_json,
        confidence=dec.structured_confidence,
        output_language=dec.output_language,
        justification=dec.justification,
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

    async def list_recent_for_feedback(
        self, session: AsyncSession, limit: int = 5
    ) -> list[AgentDecision]:
        """Return most-recent-first decisions for LLM feedback rendering.

        Includes full structured fields so the feedback block can render
        market_context/plan/confidence alongside action/symbol. Identical
        SQL to :meth:`list_recent` but with a feedback-tuned default limit
        and a distinct debug log tag — kept separate so caller-site grep
        makes the self-reflection path explicit.
        """
        with_context(logger).debug(
            "decision_repository.list_recent_for_feedback", limit=limit
        )
        stmt = (
            select(AgentDecisionORM)
            .order_by(AgentDecisionORM.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, dec: AgentDecision) -> AgentDecision:
        with_context(logger).info("decision_repository.create", iteration=dec.iteration)
        row = _domain_to_orm(dec)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def get_latest_invalidation_for_symbol(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> str | None:
        """Return the most recent non-empty ``invalidation_condition`` that
        mentioned ``symbol`` in its ``actions_taken`` JSON.

        Used by ``InvalidationMonitor`` to pull the LLM's self-authored
        invalidation text for an OPEN position (``invalidation_condition``
        lives on ``agent_decisions``, not ``positions``). Scans the latest
        decisions in reverse-timestamp order so a position re-opened after
        a close picks up the *new* invalidation, not a stale one from the
        previous lifecycle.
        """
        with_context(logger).debug(
            "decision_repository.get_latest_invalidation_for_symbol",
            symbol=symbol,
        )
        stmt = (
            select(AgentDecisionORM)
            .where(AgentDecisionORM.invalidation_condition.is_not(None))
            .order_by(AgentDecisionORM.timestamp.desc())
            .limit(50)
        )
        result = await session.execute(stmt)
        for row in result.scalars().all():
            if row.invalidation_condition is None:
                continue
            # ``actions_taken`` is a JSON array of trade dicts (see
            # TradingLoopMonitor.tick). Cheap substring match is enough —
            # symbol strings like ``BTC_USDT`` are unambiguous.
            if symbol in (row.actions_taken or ""):
                return row.invalidation_condition
        return None
