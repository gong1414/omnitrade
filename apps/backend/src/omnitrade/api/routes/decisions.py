"""GET /api/v1/decisions — most-recent AI decision rows (paginated)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from omnitrade.api.deps import get_decision_service
from omnitrade.application.decision_service import DecisionService
from omnitrade.domain.entities import AgentDecision

router = APIRouter(tags=["decisions"])


def _decision_to_dict(d: AgentDecision) -> dict[str, Any]:
    return {
        "id": d.id,
        "timestamp": d.timestamp.isoformat(),
        "iteration": d.iteration,
        "decision": d.decision,
        "market_analysis": d.market_analysis,
        "actions_taken": d.actions_taken,
        "account_value": str(d.account_value),
        "positions_count": d.positions_count,
        "correlation_id": d.correlation_id,
    }


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: DecisionService = Depends(get_decision_service),
) -> dict[str, Any]:
    """Return most-recent-first decision rows, paginated by offset/limit."""
    rows = await service.list_recent(limit=limit, offset=offset)
    return {
        "decisions": [_decision_to_dict(d) for d in rows],
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


__all__ = ["router"]
