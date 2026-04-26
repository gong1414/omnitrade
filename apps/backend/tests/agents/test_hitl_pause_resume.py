"""T9 integration coverage: paused-run resume loop in the trading agent.

Strategy mirrors ``tests/eval/test_reliability_cycle.py`` (T7): the
trading Agent's machinery is real, but the LLM is replaced by a
synthetic :class:`agno.run.agent.RunOutput` so we never issue a network
call. We exercise the pause-resolve helper directly against synthetic
``RunOutput`` shapes that match what Agno emits when an
``open_position`` tool call hits ``requires_confirmation=True``.

Three scenarios are pinned:

1. **Below threshold** — the predicate auto-confirms, the wrapper does
   NOT publish ``EVENT_RUN_PAUSED``, the cycle proceeds.
2. **Above threshold + approved** — the wrapper publishes
   ``EVENT_RUN_PAUSED`` and resolves when ``/confirm`` wakes the
   future. The paused tool is marked ``confirmed=True``.
3. **Above threshold + timeout** — the wrapper rejects after the
   bounded wait, the paused tool is marked ``confirmed=False``, and the
   cycle proceeds with a defensive hold.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omnitrade.agents.hitl import ApprovalRegistry
from omnitrade.agents.trading_agent import _resolve_pauses
from omnitrade.application.events.bus import EVENT_RUN_PAUSED, EventBus

# ---------------------------------------------------------------------- #
# Fakes                                                                    #
# ---------------------------------------------------------------------- #


class _FakeToolExec:
    """Mimic :class:`agno.models.response.ToolExecution` for the loop's needs."""

    def __init__(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        requires_confirmation: bool = True,
    ) -> None:
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.requires_confirmation = requires_confirmation
        self.confirmed: bool | None = None


class _FakeRunOutput:
    """Mimic the subset of :class:`agno.run.agent.RunOutput` the loop reads."""

    def __init__(
        self,
        *,
        run_id: str,
        paused_tools: list[_FakeToolExec],
    ) -> None:
        self.run_id = run_id
        self._paused_tools = paused_tools
        # Loop checks ``is_paused`` and ``tools_requiring_confirmation``.
        # We flip ``is_paused`` to False after the first acontinue_run.
        self._resolved = False

    @property
    def is_paused(self) -> bool:
        return not self._resolved

    @property
    def tools_requiring_confirmation(self) -> list[_FakeToolExec]:
        return list(self._paused_tools)


class _FakeAgent:
    """Replays a single ``acontinue_run`` step then reports completion."""

    def __init__(self, run: _FakeRunOutput) -> None:
        self.run = run
        self.continue_calls = 0

    async def acontinue_run(self, run_response: _FakeRunOutput, **_: Any) -> _FakeRunOutput:
        self.continue_calls += 1
        # Mark resolved so the loop exits on the next ``is_paused`` check.
        run_response._resolved = True
        return run_response


class _Settings:
    def __init__(
        self,
        *,
        threshold_usd: float = 10_000.0,
        wait_seconds: float = 0.05,
    ) -> None:
        self.hitl_open_size_threshold_usd = threshold_usd
        self.hitl_approval_wait_seconds = wait_seconds


# ---------------------------------------------------------------------- #
# Scenarios                                                                #
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_below_threshold_auto_confirms_and_does_not_publish() -> None:
    """0.1 BTC @ 50,000 = 5,000 USD ⇒ below 10,000 ⇒ no banner, auto-resume."""
    tool_exec = _FakeToolExec(
        tool_name="open_position",
        tool_args={
            "symbol": "BTC_USDT",
            "side": "long",
            "size": 0.1,
            "leverage": 5,
            "entry_price": 50_000.0,
        },
    )
    run = _FakeRunOutput(run_id="run-below", paused_tools=[tool_exec])
    agent = _FakeAgent(run)

    bus = EventBus()
    queue = bus.subscribe_queue({EVENT_RUN_PAUSED})

    registry = ApprovalRegistry()

    out = await _resolve_pauses(
        agent=agent,
        run_result=run,
        settings=_Settings(),
        event_bus=bus,
        approval_registry=registry,
    )

    assert out is run
    assert tool_exec.confirmed is True, "below threshold ⇒ auto-confirm"
    assert agent.continue_calls == 1
    assert queue.empty(), "no banner published below threshold"
    assert registry.pending_run_ids() == []


@pytest.mark.asyncio
async def test_above_threshold_publishes_and_resumes_on_approve() -> None:
    """1 BTC @ 50,000 = 50,000 USD ⇒ above threshold ⇒ banner + wait for /confirm."""
    tool_exec = _FakeToolExec(
        tool_name="open_position",
        tool_args={
            "symbol": "BTC_USDT",
            "side": "long",
            "size": 1.0,
            "leverage": 5,
            "entry_price": 50_000.0,
        },
    )
    run = _FakeRunOutput(run_id="run-above-approve", paused_tools=[tool_exec])
    agent = _FakeAgent(run)

    bus = EventBus()
    queue = bus.subscribe_queue({EVENT_RUN_PAUSED})

    registry = ApprovalRegistry()

    # Race: trigger /confirm shortly after the resolver starts waiting.
    async def _confirm_soon() -> None:
        await asyncio.sleep(0.01)
        ok = await registry.resolve("run-above-approve", "approve")
        assert ok is True

    confirmer = asyncio.create_task(_confirm_soon())
    out = await _resolve_pauses(
        agent=agent,
        run_result=run,
        settings=_Settings(wait_seconds=2.0),
        event_bus=bus,
        approval_registry=registry,
    )
    await confirmer

    assert out is run
    assert tool_exec.confirmed is True, "approval ⇒ confirmed"
    assert agent.continue_calls == 1

    # The banner was published exactly once with the expected shape.
    assert not queue.empty(), "expected EVENT_RUN_PAUSED to be published"
    event = await queue.get()
    assert event.type == EVENT_RUN_PAUSED
    assert event.payload["run_id"] == "run-above-approve"
    assert event.payload["tool_name"] == "open_position"
    assert "size" in event.payload["tool_args"]
    assert "USD" in event.payload["requires_confirmation_reason"]
    assert registry.pending_run_ids() == []


@pytest.mark.asyncio
async def test_above_threshold_rejects_on_timeout() -> None:
    """No approval within ``hitl_approval_wait_seconds`` ⇒ rejected."""
    tool_exec = _FakeToolExec(
        tool_name="open_position",
        tool_args={
            "symbol": "BTC_USDT",
            "side": "long",
            "size": 1.0,
            "leverage": 5,
            "entry_price": 50_000.0,
        },
    )
    run = _FakeRunOutput(run_id="run-timeout", paused_tools=[tool_exec])
    agent = _FakeAgent(run)

    bus = EventBus()
    registry = ApprovalRegistry()

    out = await _resolve_pauses(
        agent=agent,
        run_result=run,
        settings=_Settings(wait_seconds=0.05),
        event_bus=bus,
        approval_registry=registry,
    )

    assert out is run
    assert tool_exec.confirmed is False, "timeout ⇒ rejected"
    assert agent.continue_calls == 1
    assert registry.pending_run_ids() == []


@pytest.mark.asyncio
async def test_above_threshold_rejects_explicitly() -> None:
    """`/reject` resolves the future to ``"reject"`` ⇒ confirmed=False."""
    tool_exec = _FakeToolExec(
        tool_name="open_position",
        tool_args={"size": 2.0, "entry_price": 50_000.0},
    )
    run = _FakeRunOutput(run_id="run-reject", paused_tools=[tool_exec])
    agent = _FakeAgent(run)

    bus = EventBus()
    registry = ApprovalRegistry()

    async def _reject_soon() -> None:
        await asyncio.sleep(0.01)
        ok = await registry.resolve("run-reject", "reject")
        assert ok is True

    rejecter = asyncio.create_task(_reject_soon())
    await _resolve_pauses(
        agent=agent,
        run_result=run,
        settings=_Settings(wait_seconds=2.0),
        event_bus=bus,
        approval_registry=registry,
    )
    await rejecter

    assert tool_exec.confirmed is False
    assert registry.pending_run_ids() == []


@pytest.mark.asyncio
async def test_unexpected_paused_tool_is_auto_rejected() -> None:
    """Defensive: any tool other than ``open_position`` flagged for
    confirmation is rejected — only the open path opted in."""
    tool_exec = _FakeToolExec(
        tool_name="something_else",
        tool_args={"size": 999.0, "entry_price": 999.0},
    )
    run = _FakeRunOutput(run_id="run-other", paused_tools=[tool_exec])
    agent = _FakeAgent(run)

    bus = EventBus()
    queue = bus.subscribe_queue({EVENT_RUN_PAUSED})
    registry = ApprovalRegistry()

    await _resolve_pauses(
        agent=agent,
        run_result=run,
        settings=_Settings(),
        event_bus=bus,
        approval_registry=registry,
    )

    assert tool_exec.confirmed is False
    assert queue.empty(), "non-open tool ⇒ no banner"


# ---------------------------------------------------------------------- #
# Approval registry idempotency                                            #
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_resolve_unknown_run_id_returns_false() -> None:
    """Late ``/confirm`` for a timed-out run is a no-op (returns False).

    Routes lift this into a 404 — important so a duplicated banner click
    after the cycle wraps doesn't surface as a 500."""
    registry = ApprovalRegistry()
    woke = await registry.resolve("not-registered", "approve")
    assert woke is False
