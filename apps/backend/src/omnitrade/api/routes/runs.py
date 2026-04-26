"""POST /api/v1/runs/{run_id}/{confirm,reject} — HITL approval surface (T9).

The trading agent decorates ``open_position`` with
``requires_confirmation=True``. Whenever an open exceeds the configured
USD-notional threshold, the agent publishes ``EVENT_RUN_PAUSED`` to the
dashboard and parks an :class:`asyncio.Future` on
``ApiContainer.approval_registry`` keyed by the Agno ``run_id``. These
two endpoints resolve that future so the trading-agent wrapper resumes
the paused run with ``confirmed=True`` (approve) or ``False`` (reject).

Both endpoints are intentionally tiny — the heavy lifting (pause loop,
event publish, decision recording) lives in
:mod:`omnitrade.agents.trading_agent`. This module only translates HTTP
to a registry call.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/runs", tags=["runs"])


def _registry(request: Request) -> Any:
    container = getattr(request.app.state, "api_container", None)
    if container is None:
        raise HTTPException(503, "container not initialised")
    registry = getattr(container, "approval_registry", None)
    if registry is None:
        raise HTTPException(503, "approval_registry not wired")
    return registry


@router.post("/{run_id}/confirm")
async def confirm_run(run_id: str, request: Request) -> dict[str, Any]:
    """Approve a paused run.

    Returns ``{"status":"resolved", "decision":"approve"}`` when an
    awaiter was wakened, ``404`` otherwise (no pending approval — either
    the run already timed out or this is a duplicate click).
    """
    registry = _registry(request)
    woke = await registry.resolve(run_id, "approve")
    if not woke:
        raise HTTPException(404, "no pending approval for this run_id")
    return {"status": "resolved", "decision": "approve", "run_id": run_id}


@router.post("/{run_id}/reject")
async def reject_run(run_id: str, request: Request) -> dict[str, Any]:
    """Reject a paused run.

    Mirror of :func:`confirm_run` but resolves the future with
    ``"reject"`` so the trading-agent wrapper sets ``confirmed=False``
    on the paused tool execution.
    """
    registry = _registry(request)
    woke = await registry.resolve(run_id, "reject")
    if not woke:
        raise HTTPException(404, "no pending approval for this run_id")
    return {"status": "resolved", "decision": "reject", "run_id": run_id}


__all__ = ["router"]
