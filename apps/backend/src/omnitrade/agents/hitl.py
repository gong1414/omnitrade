"""Human-in-the-loop approval helpers for the trading Agent (T9).

When an LLM-emitted ``open_position`` decision exceeds a configured USD
notional threshold, the trading-agent wrapper pauses the Agno run, asks
the operator to approve via the dashboard banner, and resumes only after
the operator hits ``POST /api/v1/runs/{run_id}/{confirm,reject}``.

This module owns:
  * :func:`open_size_usd` — coerce tool args into a USD-notional number.
  * :func:`should_require_confirmation` — predicate-style helper that
    returns ``True`` when the open exceeds the threshold. Pure / sync /
    side-effect-free so unit tests can hammer it cheaply. The trading
    agent's wrapper is the only caller in production.
  * :class:`ApprovalRegistry` — in-memory pending-approval store. The
    trading agent registers a per-run :class:`asyncio.Future`; the
    ``/confirm`` and ``/reject`` API routes resolve the matching future.

The registry is intentionally process-local (no Redis / DB). HITL
approvals are bounded by the cycle's ``hitl_approval_wait_seconds`` —
on timeout the future is rejected, the cycle records a defensive
``hold``, and the registry entry is reaped. Subsequent approve/reject
calls for an unknown ``run_id`` return ``False`` to keep the API
idempotent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)


# Tool name the trading agent decorates with ``requires_confirmation=True``
# is registered as ``open_position`` (Function name, see
# :mod:`omnitrade.agents.tools.decision_schemas`). Re-exported here so
# the API + trading-agent wrapper agree on the canonical string.
HITL_OPEN_TOOL_NAME = "open_position"


def open_size_usd(args: Mapping[str, Any] | None) -> float:
    """Best-effort USD-notional from an ``open_position`` tool-call args dict.

    Agno passes tool args through as a dict (parsed from the JSON the
    model emitted). Most opens carry ``size`` (contracts) and may carry
    a price reference under ``entry_price`` / ``price``. We fall back
    to ``stop_loss`` / ``take_profit`` only as a last resort because
    those bracket prices are usually within ~1-3 % of the entry, which
    keeps the threshold check directionally correct even when the LLM
    forgets to echo the entry price.

    Returns ``0.0`` for any malformed input — the predicate's
    above-threshold check then fails closed (no pause), matching the
    "default = no behavior change for routine opens" contract.
    """
    if not isinstance(args, Mapping):
        return 0.0

    def _coerce(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    size = _coerce(args.get("size"))
    if size is None or size <= 0.0:
        return 0.0

    # Prefer an explicit entry/price; fall back through the usual
    # synonyms before reaching the bracket prices. This mirrors what
    # the LLM is taught to emit in the ``record_open_decision`` schema.
    for key in ("entry_price", "price", "mark_price", "stop_loss", "take_profit"):
        candidate = _coerce(args.get(key))
        if candidate is not None and candidate > 0.0:
            return float(size) * float(candidate)
    return 0.0


def should_require_confirmation(
    args: Mapping[str, Any] | None,
    *,
    threshold_usd: float,
) -> bool:
    """Return ``True`` when an ``open_position`` call should pause for approval.

    The trading-agent wrapper invokes this against the paused
    :class:`ToolExecution`'s ``tool_args`` dict. ``threshold_usd`` ≤ 0
    falls through to ``False`` (no pause) so an operator can effectively
    disable HITL by setting ``HITL_OPEN_SIZE_THRESHOLD_USD=0``.
    """
    if threshold_usd <= 0.0:
        return False
    return open_size_usd(args) > threshold_usd


# ---------------------------------------------------------------------- #
# Approval registry                                                       #
# ---------------------------------------------------------------------- #


ApprovalDecision = Literal["approve", "reject"]


class ApprovalRegistry:
    """In-process map of ``run_id`` → pending approval :class:`asyncio.Future`.

    The trading-agent wrapper calls :meth:`register` before publishing
    ``EVENT_RUN_PAUSED`` and awaits the returned future (with a wall
    timeout). The ``/confirm`` and ``/reject`` API routes call
    :meth:`resolve` to wake the wrapper. :meth:`unregister` is the
    cleanup hook (cycle finished / timed out).
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str) -> asyncio.Future[ApprovalDecision]:
        """Reserve a future for ``run_id``. Idempotent within a process.

        If the same ``run_id`` is registered twice (shouldn't happen —
        Agno run-ids are unique), the existing future is returned so a
        late ``/confirm`` still wakes the right awaiter.
        """
        async with self._lock:
            existing = self._pending.get(run_id)
            if existing is not None and not existing.done():
                return existing
            loop = asyncio.get_running_loop()
            future: asyncio.Future[ApprovalDecision] = loop.create_future()
            self._pending[run_id] = future
            return future

    async def resolve(self, run_id: str, decision: ApprovalDecision) -> bool:
        """Resolve a pending approval. Returns ``True`` when a future was waiting.

        ``False`` (no-op) is returned when no awaiter is registered —
        either because the cycle already timed out, or because the
        operator double-clicked. The API routes surface this as a 404.
        """
        async with self._lock:
            future = self._pending.get(run_id)
            if future is None or future.done():
                return False
            future.set_result(decision)
            return True

    async def unregister(self, run_id: str) -> None:
        """Drop the registry entry. Called by the awaiter on
        completion/timeout so the dict doesn't leak across cycles."""
        async with self._lock:
            self._pending.pop(run_id, None)

    def pending_run_ids(self) -> list[str]:
        """Snapshot of currently-pending run-ids. Diagnostic only."""
        return [rid for rid, f in self._pending.items() if not f.done()]


__all__ = [
    "HITL_OPEN_TOOL_NAME",
    "ApprovalDecision",
    "ApprovalRegistry",
    "open_size_usd",
    "should_require_confirmation",
]
