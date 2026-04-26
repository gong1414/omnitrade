"""Phase 4.5 monitor holder + workflow late-binding tests.

The trading workflow is built before the FastAPI lifespan creates
the monitor — see :class:`omnitrade.api.agent_os_app.MonitorHolder`.
These tests verify:

1. Write-once semantics — calling ``set_monitor`` twice keeps the
   first binding (and only logs a warning).
2. ``get_monitor`` raises a clear error when called before binding.
3. ``aget_monitor`` blocks on the readiness event until the monitor
   binds, then returns it.
4. The trading workflow's tick step raises when the holder is empty
   (so AgentOS marks the run as failed instead of silently completing).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omnitrade.api.agent_os_app import MonitorHolder
from omnitrade.application.trading_workflow import build_agno_trading_workflow


class _FakeMonitor:
    """Stand-in for :class:`TradingLoopMonitor` — the only contract
    needed for these tests is being object-identifiable."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.tick_calls = 0

    async def tick(self) -> None:
        self.tick_calls += 1


def test_monitor_holder_get_before_bind_raises() -> None:
    holder = MonitorHolder()
    with pytest.raises(RuntimeError, match="not yet bound"):
        holder.get_monitor()


def test_monitor_holder_set_then_get() -> None:
    holder = MonitorHolder()
    monitor = _FakeMonitor("a")
    holder.set_monitor(monitor)  # type: ignore[arg-type] — duck-typed test stub
    assert holder.get_monitor() is monitor


def test_monitor_holder_write_once_keeps_first() -> None:
    holder = MonitorHolder()
    first = _FakeMonitor("first")
    second = _FakeMonitor("second")
    holder.set_monitor(first)  # type: ignore[arg-type]
    holder.set_monitor(second)  # type: ignore[arg-type] — should be ignored
    assert holder.get_monitor() is first


@pytest.mark.asyncio
async def test_monitor_holder_aget_waits_for_bind() -> None:
    holder = MonitorHolder()
    monitor = _FakeMonitor("late")

    async def _bind_after(delay: float) -> None:
        await asyncio.sleep(delay)
        holder.set_monitor(monitor)  # type: ignore[arg-type]

    asyncio.create_task(_bind_after(0.05))
    bound = await holder.aget_monitor(timeout=1.0)
    assert bound is monitor


@pytest.mark.asyncio
async def test_monitor_holder_aget_times_out_when_never_bound() -> None:
    holder = MonitorHolder()
    with pytest.raises(RuntimeError, match="monitor not bound after"):
        await holder.aget_monitor(timeout=0.05)


@pytest.mark.asyncio
async def test_workflow_tick_propagates_failure_when_monitor_missing() -> None:
    """Review issue #3 — schedule run must be marked as failed, not
    silently 'completed', when the monitor isn't bound yet.

    Agno's :class:`Workflow` retries failing steps internally (default
    ``max_retries`` on the Step) and returns a run response whose
    ``step_results[*].success`` is False instead of re-raising. The
    AgentOS scheduler executor polls the run record and reports the
    schedule failure based on this status, so the contract we test is:
    *every step result must be marked as a failure*.
    """

    class _StubSettings:
        pass

    workflow = build_agno_trading_workflow(
        lambda: None,  # accessor returns None — simulates unbound holder
        _StubSettings(),  # type: ignore[arg-type]
        db=None,
    )

    result = await workflow.arun("ignored")
    step_results = getattr(result, "step_results", None) or []
    assert step_results, "expected at least one step_result on the workflow run"
    assert all(not sr.success for sr in step_results), (
        "workflow steps must all be marked as failures when monitor is missing"
    )
    assert any(
        "monitor not initialized" in (sr.error or "") for sr in step_results
    ), "step error message must point at the unbound-monitor cause"
