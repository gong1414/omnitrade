"""T9 unit coverage for the HITL ``open_position`` threshold.

The trading agent decorates ``open_position`` with
``requires_confirmation=True`` (so Agno pauses every open) and the
trading-agent wrapper consults
:func:`omnitrade.agents.hitl.should_require_confirmation` per call to
decide whether to auto-confirm or escalate to a human.

These tests pin three contracts:

1. The predicate is True only when the USD notional exceeds the
   threshold and the args are well-formed.
2. The predicate is False for non-open decisions (close / partial /
   hold) — they were never wrapped.
3. The wrapped tool list registers ``open_position`` as an Agno
   :class:`Function` with ``requires_confirmation=True``. Below the
   threshold the predicate returns False, so the trading-agent wrapper
   must still see the Agno pause but auto-confirm without surfacing the
   banner.
"""

from __future__ import annotations

from typing import Any

from agno.tools.function import Function

from omnitrade.agents.hitl import (
    HITL_OPEN_TOOL_NAME,
    open_size_usd,
    should_require_confirmation,
)
from omnitrade.agents.tools.decision_schemas import (
    DecisionRecorder,
    build_decision_tools,
    wrap_open_position_for_hitl,
)


# ---------------------------------------------------------------------- #
# Predicate                                                                #
# ---------------------------------------------------------------------- #


THRESHOLD = 10_000.0


def test_predicate_true_when_notional_exceeds_threshold() -> None:
    """1 contract @ 50,000 USD = 50,000 notional ⇒ above threshold."""
    args = {
        "symbol": "BTC_USDT",
        "side": "long",
        "size": 1.0,
        "leverage": 5,
        "entry_price": 50_000.0,
    }
    assert should_require_confirmation(args, threshold_usd=THRESHOLD) is True


def test_predicate_false_when_notional_at_or_below_threshold() -> None:
    """0.1 contract @ 50,000 USD = 5,000 notional ⇒ below threshold ⇒ False.

    Boundary case: at-threshold also returns False (strict ``>``), so
    operators choosing 10,000 see no pause for exactly 10,000 USD opens.
    """
    args = {
        "symbol": "BTC_USDT",
        "side": "long",
        "size": 0.1,
        "leverage": 5,
        "entry_price": 50_000.0,
    }
    assert should_require_confirmation(args, threshold_usd=THRESHOLD) is False

    # Exactly at the threshold (use strict `>` semantics).
    at_threshold = {**args, "size": 0.2}  # 0.2 * 50k = 10,000 exactly
    assert should_require_confirmation(at_threshold, threshold_usd=THRESHOLD) is False


def test_predicate_false_for_malformed_args() -> None:
    """Missing size or price ⇒ notional 0 ⇒ no pause (fail-closed)."""
    assert should_require_confirmation({}, threshold_usd=THRESHOLD) is False
    assert should_require_confirmation({"size": 1.0}, threshold_usd=THRESHOLD) is False
    assert should_require_confirmation(
        {"size": 1.0, "entry_price": "not-a-number"},
        threshold_usd=THRESHOLD,
    ) is False
    assert should_require_confirmation(None, threshold_usd=THRESHOLD) is False


def test_predicate_false_when_threshold_disabled() -> None:
    """``threshold_usd <= 0`` is the operator kill-switch ⇒ never pause."""
    args = {"size": 1.0, "entry_price": 50_000.0}
    assert should_require_confirmation(args, threshold_usd=0.0) is False
    assert should_require_confirmation(args, threshold_usd=-1.0) is False


def test_predicate_uses_stop_loss_as_price_fallback() -> None:
    """When the LLM omits entry_price, fall back to stop_loss / take_profit
    so the threshold check stays directionally correct.

    Stop-loss prices are usually within 1-3% of entry so this fallback
    will misclassify only by a similarly small margin — the user can
    adjust ``HITL_OPEN_SIZE_THRESHOLD_USD`` to compensate when this
    bothers them.
    """
    args = {"size": 1.0, "stop_loss": 50_000.0}
    assert should_require_confirmation(args, threshold_usd=THRESHOLD) is True


def test_open_size_usd_returns_zero_for_negative_size() -> None:
    """Negative or zero ``size`` ⇒ notional 0 ⇒ never pause."""
    assert open_size_usd({"size": -1.0, "entry_price": 50_000.0}) == 0.0
    assert open_size_usd({"size": 0.0, "entry_price": 50_000.0}) == 0.0


# ---------------------------------------------------------------------- #
# Tool registration                                                        #
# ---------------------------------------------------------------------- #


def test_open_position_tool_carries_requires_confirmation() -> None:
    """After ``wrap_open_position_for_hitl`` the open tool is an Agno
    :class:`Function` with ``requires_confirmation=True``.

    This is the structural contract the trading-agent factory relies on
    — without ``requires_confirmation=True`` Agno would never emit the
    ``RunPausedEvent`` the wrapper consumes.
    """
    recorder = DecisionRecorder()
    tools = wrap_open_position_for_hitl(build_decision_tools(recorder))

    open_tool = next(
        (
            t
            for t in tools
            if isinstance(t, Function) and t.name == HITL_OPEN_TOOL_NAME
        ),
        None,
    )
    assert open_tool is not None, (
        f"open_position not wrapped as Function; tools={[type(t).__name__ for t in tools]}"
    )
    assert open_tool.requires_confirmation is True


def test_other_decision_tools_do_not_require_confirmation() -> None:
    """Only ``open_position`` should pause — close / partial / hold stay
    plain async callables so Agno auto-converts them with
    ``requires_confirmation=False`` (no pause path)."""
    recorder = DecisionRecorder()
    tools = wrap_open_position_for_hitl(build_decision_tools(recorder))

    non_open = [t for t in tools if not (isinstance(t, Function) and t.name == HITL_OPEN_TOOL_NAME)]
    assert len(non_open) == 3
    for t in non_open:
        # Plain async callable — no Agno Function metadata, no pause flag.
        assert not isinstance(t, Function)
        # Predicate against an empty args dict ⇒ never pause.
        assert should_require_confirmation({}, threshold_usd=THRESHOLD) is False


def test_predicate_is_inert_for_non_open_args() -> None:
    """Close / partial / hold args have no ``size`` ⇒ predicate False.

    The trading-agent wrapper only ever invokes the predicate against
    ``open_position`` paused tool args, but a misrouted call (e.g.
    accidentally passing close-tool args) must not pause either.
    """
    close_args: dict[str, Any] = {"symbol": "BTC_USDT", "reason": {}}
    assert should_require_confirmation(close_args, threshold_usd=THRESHOLD) is False

    partial_args: dict[str, Any] = {"symbol": "BTC_USDT", "percentage": 50, "reason": {}}
    assert should_require_confirmation(partial_args, threshold_usd=THRESHOLD) is False

    hold_args: dict[str, Any] = {"reason": {}}
    assert should_require_confirmation(hold_args, threshold_usd=THRESHOLD) is False
