"""GET /api/v1/decisions — most-recent AI decision rows (paginated).

When called with ``?include=trace``, each decision is enriched with a
``trace`` array of stream events reconstructed from the matched Agno run
in ``ai.agno_sessions``. Each trace event is one of:

  - ``thinking``  — assistant.reasoning_content (chain-of-thought)
  - ``tool_call`` — assistant.tool_calls[*] (LLM-issued MCP / decision tool)
  - ``tool_result`` — role=tool message body (the tool's response)

Trace messages are matched to decisions by Postgres-stored Agno run
``created_at`` (unix seconds) within ±5 minutes of the decision's
timestamp. Decisions older than the active Agno session window simply
get ``trace: []``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from omnitrade.api.container import ApiContainer
from omnitrade.api.deps import get_container, get_decision_service
from omnitrade.application.decision_service import DecisionService
from omnitrade.domain.entities import AgentDecision

router = APIRouter(tags=["decisions"])


_AGNO_SESSION_ID = "omnitrade-trading"
"""Stable session id Agno uses across cycles (see trading_agent.py)."""

_TRACE_MATCH_WINDOW_SECONDS = 300
"""How far the run's created_at can drift from the decision's timestamp
before we treat them as unrelated. Five minutes is generous — production
cycles complete in well under that — but tolerates wall-clock skew."""


def _decision_to_dict(d: AgentDecision) -> dict[str, Any]:
    return {
        "id": d.id,
        "timestamp": d.timestamp.isoformat(),
        "iteration": d.iteration,
        "decision": d.decision,
        "symbol": d.symbol,
        "side": d.side,
        "market_analysis": d.market_analysis,
        "actions_taken": d.actions_taken,
        "account_value": str(d.account_value),
        "positions_count": d.positions_count,
        "run_id": d.run_id,
        "market_context": d.market_context,
        "gates_passed": d.gates_passed,
        "invalidation_condition": d.invalidation_condition,
        "plan": d.plan,
        "structured_confidence": d.structured_confidence,
        "output_language": d.output_language,
        "justification": d.justification,
    }


def _flatten_run_to_trace(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Project an Agno run's ``messages`` into the dashboard trace shape.

    The frontend ``buildStreamFromDecisions`` adapter is decision-centric
    and doesn't know about Agno — keeping the projection in the backend
    means the wire contract stays stable even if the underlying run
    schema drifts (e.g. a future Agno upgrade renaming fields).
    """
    out: list[dict[str, Any]] = []
    messages = run.get("messages") or []
    if not isinstance(messages, list):
        return out
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        created_at = msg.get("created_at")
        # Chain-of-thought lives on assistant messages; emit it
        # independently so the "思考" tab gets its own bubble even when
        # the same message also carried tool_calls.
        reasoning = msg.get("reasoning_content")
        if role == "assistant" and isinstance(reasoning, str) and reasoning.strip():
            out.append(
                {
                    "kind": "thinking",
                    "role": "assistant",
                    "content": reasoning,
                    "created_at": created_at,
                }
            )
        if role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = (tc.get("function") or {}) if isinstance(tc.get("function"), dict) else {}
                    name = fn.get("name") or tc.get("tool_name") or "tool"
                    raw_args = fn.get("arguments") if "arguments" in fn else tc.get("tool_args")
                    args: Any
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except Exception:
                            args = raw_args
                    else:
                        args = raw_args
                    out.append(
                        {
                            "kind": "tool_call",
                            "id": tc.get("id"),
                            "tool": name,
                            "args": args,
                            "created_at": created_at,
                        }
                    )
        if role == "tool":
            out.append(
                {
                    "kind": "tool_result",
                    "id": msg.get("tool_call_id"),
                    "tool": msg.get("tool_name") or "tool",
                    "preview": (msg.get("content") or "")[:1024],
                    "created_at": created_at,
                }
            )
    return out


async def _fetch_runs(container: ApiContainer) -> list[dict[str, Any]]:
    """Pull the JSONB ``runs`` array for the trading session, newest last.

    Returns an empty list if the session row is absent (no Agno cycles
    have completed yet, or the user is on an older snapshot).
    """
    session = container.session_factory()
    try:
        result = await session.execute(
            text(
                "SELECT runs FROM ai.agno_sessions WHERE session_id = :sid"
            ),
            {"sid": _AGNO_SESSION_ID},
        )
        row = result.first()
    finally:
        await session.close()
    if row is None or row[0] is None:
        return []
    runs = row[0]
    return list(runs) if isinstance(runs, list) else []


def _attach_traces(decisions: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    """Mutate ``decisions`` in place, adding ``trace`` to each row.

    Pairs each decision to the run with closest ``created_at`` within
    :data:`_TRACE_MATCH_WINDOW_SECONDS`. Each run can only be matched to
    one decision — once consumed, it's removed from the candidate pool
    so two adjacent decisions don't both inherit the same trace.
    """
    pool = list(runs)  # consumable copy
    for d in decisions:
        ts = d.get("timestamp")
        if not isinstance(ts, str):
            d["trace"] = []
            continue
        from datetime import datetime

        try:
            dec_epoch = int(datetime.fromisoformat(ts).timestamp())
        except ValueError:
            d["trace"] = []
            continue
        best_idx: int | None = None
        best_delta = _TRACE_MATCH_WINDOW_SECONDS + 1
        for idx, run in enumerate(pool):
            run_created = run.get("created_at")
            if not isinstance(run_created, (int, float)):
                continue
            delta = abs(int(run_created) - dec_epoch)
            if delta < best_delta:
                best_delta = delta
                best_idx = idx
        if best_idx is None:
            d["trace"] = []
            continue
        run = pool.pop(best_idx)
        d["trace"] = _flatten_run_to_trace(run)


@router.get("/decisions")
async def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include: str | None = Query(
        default=None,
        description=(
            "Comma-separated extras. Currently supports 'trace' to inline "
            "the matched Agno run trace under each decision."
        ),
    ),
    service: DecisionService = Depends(get_decision_service),
    container: ApiContainer = Depends(get_container),
) -> dict[str, Any]:
    """Return most-recent-first decision rows, paginated by offset/limit."""
    rows = await service.list_recent(limit=limit, offset=offset)
    decisions = [_decision_to_dict(d) for d in rows]
    extras = {p.strip() for p in (include or "").split(",") if p.strip()}
    if "trace" in extras:
        runs = await _fetch_runs(container)
        _attach_traces(decisions, runs)
    return {
        "decisions": decisions,
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


__all__ = ["router"]
