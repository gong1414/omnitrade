"""DecisionService — persists ``AgentDecision`` rows and emits events.

This is the thin write-side companion to ``DecisionRepository``; it owns
the event fan-out so the UI learns about new decisions in real time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.events import EVENT_DECISION_UPDATE, EventBus
from omnitrade.domain.entities import AgentDecision
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from omnitrade.observability.trace_context import get_correlation_id, with_context

logger = structlog.get_logger(__name__)


SessionFactory = Callable[[], Awaitable[AsyncSession]]


def _decision_to_dict(dec: AgentDecision) -> dict[str, Any]:
    return {
        "id": dec.id,
        "timestamp": dec.timestamp.isoformat(),
        "iteration": dec.iteration,
        "decision": dec.decision,
        "symbol": dec.symbol,
        "side": dec.side,
        "market_analysis": dec.market_analysis,
        "actions_taken": dec.actions_taken,
        "account_value": str(dec.account_value),
        "positions_count": dec.positions_count,
        "correlation_id": dec.correlation_id,
        "justification": dec.justification,
    }


class DecisionService:
    """Application service for agent decision persistence + broadcast."""

    def __init__(
        self,
        *,
        repo: DecisionRepository,
        session_factory: SessionFactory,
        event_bus: EventBus,
    ) -> None:
        self._repo = repo
        self._session_factory = session_factory
        self._event_bus = event_bus

    async def record(
        self,
        *,
        iteration: int,
        decision_text: str,
        market_analysis: str,
        actions_taken: str,
        account_value: Decimal,
        positions_count: int,
        timestamp: datetime | None = None,
        symbol: str | None = None,
        side: str | None = None,
        # StructuredReason fields — all optional; None means legacy row (DB NULLs)
        market_context: str | None = None,
        gates_passed: list[str] | None = None,
        invalidation_condition: str | None = None,
        plan: dict[str, Any] | None = None,
        structured_confidence: float | None = None,
        output_language: str | None = None,
        justification: str | None = None,
        # Transient, WS-only extras. Not persisted, merged into the
        # ``decision_update`` payload so clients can render cycle telemetry
        # (e.g. PipelineStatus stage timings) without a DB migration.
        ws_extras: dict[str, Any] | None = None,
    ) -> AgentDecision:
        """Persist an ``AgentDecision`` row and publish a ``decision_update``."""
        ts = timestamp if timestamp is not None else datetime.now(tz=UTC)
        dec = AgentDecision(
            timestamp=ts,
            iteration=iteration,
            market_analysis=market_analysis,
            decision=decision_text,
            actions_taken=actions_taken,
            account_value=account_value,
            positions_count=positions_count,
            correlation_id=get_correlation_id(),
            symbol=symbol,
            side=side,
            market_context=market_context,
            gates_passed=gates_passed,
            invalidation_condition=invalidation_condition,
            plan=plan,
            structured_confidence=structured_confidence,
            output_language=output_language,
            justification=justification,
        )
        with_context(logger).info("decision_service.record", iteration=iteration)

        session = await self._session_factory()
        try:
            persisted = await self._repo.create(session, dec)
            await session.commit()
        finally:
            await session.close()

        payload = _decision_to_dict(persisted)
        if ws_extras:
            payload.update(ws_extras)
        await self._event_bus.publish(EVENT_DECISION_UPDATE, payload)
        return persisted

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[AgentDecision]:
        """Return most-recent-first decision rows with simple offset pagination."""
        session = await self._session_factory()
        try:
            # list_recent already sorts desc by timestamp; apply offset client-side
            rows = await self._repo.list_recent(session, limit=limit + offset)
        finally:
            await session.close()
        return rows[offset : offset + limit]


__all__ = ["DecisionService", "SessionFactory"]
