"""POST /api/v1/runs/{run_id}/{confirm,reject} — HITL approval routes (T9)."""

from __future__ import annotations

import asyncio

import pytest

from omnitrade.agents.hitl import ApprovalRegistry


@pytest.mark.asyncio
async def test_confirm_404_when_no_pending_approval(api_client) -> None:  # type: ignore[no-untyped-def]
    """No registered run_id ⇒ idempotent 404 (NOT a 500)."""
    resp = await api_client.post("/api/v1/runs/no-such-run/confirm")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_404_when_no_pending_approval(api_client) -> None:  # type: ignore[no-untyped-def]
    """Mirror of /confirm: rejecting an unknown run is idempotent 404."""
    resp = await api_client.post("/api/v1/runs/no-such-run/reject")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_resolves_pending_future(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    """A pending approval is resolved to ``"approve"`` on POST /confirm."""
    registry: ApprovalRegistry = api_app.state.api_container.approval_registry
    future = await registry.register("run-confirm")
    try:
        resp = await api_client.post("/api/v1/runs/run-confirm/confirm")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "status": "resolved",
            "decision": "approve",
            "run_id": "run-confirm",
        }
        # The future was woken with "approve".
        decision = await asyncio.wait_for(future, timeout=1.0)
        assert decision == "approve"
    finally:
        await registry.unregister("run-confirm")


@pytest.mark.asyncio
async def test_reject_resolves_pending_future(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    """Mirror of /confirm: a pending approval resolves to ``"reject"``."""
    registry: ApprovalRegistry = api_app.state.api_container.approval_registry
    future = await registry.register("run-reject")
    try:
        resp = await api_client.post("/api/v1/runs/run-reject/reject")
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "reject"
        decision = await asyncio.wait_for(future, timeout=1.0)
        assert decision == "reject"
    finally:
        await registry.unregister("run-reject")


@pytest.mark.asyncio
async def test_double_confirm_returns_404(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    """Operator double-clicks ⇒ second POST is a 404 (already resolved)."""
    registry: ApprovalRegistry = api_app.state.api_container.approval_registry
    await registry.register("run-double")
    try:
        first = await api_client.post("/api/v1/runs/run-double/confirm")
        assert first.status_code == 200
        # Future already resolved, so the second click is a no-op.
        second = await api_client.post("/api/v1/runs/run-double/confirm")
        assert second.status_code == 404
    finally:
        await registry.unregister("run-double")
