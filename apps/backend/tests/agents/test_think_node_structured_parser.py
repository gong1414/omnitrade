"""Tests for the dual-path _parse_decision_from_tool_call (PR-B1 Step 4).

Coverage matrix:
  - flat string reason → Decision.reasoning=string, 6 new fields all None (legacy path)
  - dict reason (hold, plan=None) → new fields populated, plan=None
  - dict reason (open, plan complete) → all 6 new fields populated
  - dict reason missing required field (market_context) → StructuredOutputContractError
  - dict reason confidence out of range → StructuredOutputContractError
  - Every tool name (hold, open_position, close_position, partial_close) in both modes

PR-B1 constraint: StructuredOutputContractError has no opt-out flag (Principle 4).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from omnitrade.agents.errors import StructuredOutputContractError
from omnitrade.agents.think_node import _parse_decision_from_tool_call
from omnitrade.domain.entities import Decision

# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

_FLAT_REASON = "no clear signal, staying flat"

_STRUCTURED_HOLD_REASON: dict = {
    "market_context": "BTC is trading in a tight range with no directional bias.",
    "gates_passed": [],
    "invalidation_condition": "Daily close above 44000 USDT would signal breakout.",
    "plan": None,
    "confidence": 0.45,
    "justification": (
        "No strong trend or momentum signal is present. RSI at 50 and Bollinger Bands "
        "compressed indicate a consolidation phase. Holding is correct until a clear "
        "breakout or breakdown occurs. Risk-reward on any entry is unfavourable given "
        "the ambiguous regime."
    ),
    "output_language": "zh",
}

_STRUCTURED_OPEN_REASON: dict = {
    "market_context": (
        "BTC is in a sustained uptrend confirmed by EMA20 > EMA50 > EMA200. RSI holding "
        "above 58 with MACD bullish crossover signals continued momentum."
    ),
    "gates_passed": [
        "EMA alignment gate: EMA20 > EMA50 > EMA200 confirms primary uptrend",
        "RSI momentum gate: RSI 58 above midline in bullish territory",
    ],
    "invalidation_condition": "Daily close below 42000 USDT would invalidate bullish bias.",
    "plan": {
        "entry": 43500.0,
        "stop_loss": 41800.0,
        "take_profit_1": 46000.0,
        "take_profit_2": 49000.0,
        "risk_usd": 170.0,
        "r_multiple_target": 2.1,
    },
    "confidence": 0.72,
    "justification": (
        "Strong trend continuation setup with EMA stack aligned and RSI showing bullish "
        "momentum. MACD crossover confirms the entry thesis. Stop-loss placed below the "
        "most recent swing low. Risk-reward of 2.1R satisfies minimum threshold. "
        "Alternative (hold) rejected due to clear directional conviction."
    ),
    "output_language": "en",
}

# ---------------------------------------------------------------------------
# Legacy flat-string path: all 4 tool names
# ---------------------------------------------------------------------------


def test_hold_flat_reason_legacy_path() -> None:
    """hold + flat string → reasoning set, 6 structured fields all None."""
    d = _parse_decision_from_tool_call("hold", {"reason": _FLAT_REASON})
    assert d.action == "hold"
    assert d.reasoning == _FLAT_REASON
    _assert_structured_fields_none(d)


def test_no_action_flat_reason_legacy_path() -> None:
    """no_action alias + flat string → legacy path."""
    d = _parse_decision_from_tool_call("no_action", {"reason": "market unclear"})
    assert d.action == "hold"
    assert d.reasoning == "market unclear"
    _assert_structured_fields_none(d)


def test_open_position_flat_reason_legacy_path() -> None:
    """open_position + flat reasoning string → legacy path."""
    d = _parse_decision_from_tool_call(
        "open_position",
        {
            "symbol": "BTC",
            "side": "long",
            "leverage": 10,
            "size": 20,
            "reason": _FLAT_REASON,
            "reasoning": _FLAT_REASON,
        },
    )
    assert d.action == "open"
    assert d.reasoning == _FLAT_REASON
    _assert_structured_fields_none(d)


def test_openPosition_flat_reason_legacy_path() -> None:
    """openPosition alias + flat reasoning string → legacy path."""
    d = _parse_decision_from_tool_call(
        "openPosition",
        {
            "symbol": "ETH",
            "side": "short",
            "leverage": 5,
            "positionSizePercent": 10,
            "reason": "momentum fading",
            "reasoning": "momentum fading",
        },
    )
    assert d.action == "open"
    _assert_structured_fields_none(d)


def test_close_position_flat_reason_legacy_path() -> None:
    """close_position + flat reasoning → legacy path, close action."""
    d = _parse_decision_from_tool_call(
        "close_position",
        {"symbol": "BTC", "percentage": 100, "reason": _FLAT_REASON, "reasoning": _FLAT_REASON},
    )
    assert d.action == "close"
    assert d.reasoning == _FLAT_REASON
    _assert_structured_fields_none(d)


def test_closePosition_partial_flat_reason_legacy_path() -> None:
    """closePosition with <100% + flat reasoning → partial_close, legacy path."""
    d = _parse_decision_from_tool_call(
        "closePosition",
        {"symbol": "ETH", "percentage": 50, "reason": _FLAT_REASON, "reasoning": _FLAT_REASON},
    )
    assert d.action == "partial_close"
    assert d.close_percentage == Decimal(50)
    _assert_structured_fields_none(d)


def test_partial_close_position_flat_reason_legacy_path() -> None:
    """partial_close_position + flat reasoning → legacy path."""
    d = _parse_decision_from_tool_call(
        "partial_close_position",
        {
            "symbol": "SOL",
            "percentage": 30,
            "reason": _FLAT_REASON,
            "reasoning": _FLAT_REASON,
        },
    )
    assert d.action == "partial_close"
    _assert_structured_fields_none(d)


# ---------------------------------------------------------------------------
# Structured dict path: hold (plan=None)
# ---------------------------------------------------------------------------


def test_hold_structured_reason_plan_none() -> None:
    """hold + dict reason with plan=None → new fields populated, plan=None."""
    d = _parse_decision_from_tool_call("hold", {"reason": _STRUCTURED_HOLD_REASON})
    assert d.action == "hold"
    assert d.reasoning == _STRUCTURED_HOLD_REASON["justification"]
    assert d.market_context == _STRUCTURED_HOLD_REASON["market_context"]
    assert d.gates_passed == []
    assert d.invalidation_condition == _STRUCTURED_HOLD_REASON["invalidation_condition"]
    assert d.plan is None
    assert d.structured_confidence == pytest.approx(0.45)
    assert d.output_language == "zh"


def test_no_action_structured_reason() -> None:
    """no_action alias + dict reason → same structured path as hold."""
    d = _parse_decision_from_tool_call("no_action", {"reason": _STRUCTURED_HOLD_REASON})
    assert d.action == "hold"
    assert d.market_context is not None
    assert d.structured_confidence == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Structured dict path: open_position (plan complete)
# ---------------------------------------------------------------------------


def test_open_position_structured_reason_full_plan() -> None:
    """open_position + dict reason with complete plan → all 6 fields filled."""
    d = _parse_decision_from_tool_call(
        "open_position",
        {
            "symbol": "BTC",
            "side": "long",
            "leverage": 10,
            "size": 20,
            "reason": _STRUCTURED_OPEN_REASON,
        },
    )
    assert d.action == "open"
    assert d.reasoning == _STRUCTURED_OPEN_REASON["justification"]
    assert d.market_context == _STRUCTURED_OPEN_REASON["market_context"]
    assert d.gates_passed == _STRUCTURED_OPEN_REASON["gates_passed"]
    assert d.invalidation_condition == _STRUCTURED_OPEN_REASON["invalidation_condition"]
    assert d.plan is not None
    assert d.plan["entry"] == pytest.approx(43500.0)
    assert d.plan["stop_loss"] == pytest.approx(41800.0)
    assert d.plan["take_profit_1"] == pytest.approx(46000.0)
    assert d.structured_confidence == pytest.approx(0.72)
    assert d.output_language == "en"


def test_openPosition_structured_reason_full_plan() -> None:
    """openPosition alias + dict reason → same structured path."""
    d = _parse_decision_from_tool_call(
        "openPosition",
        {
            "symbol": "ETH",
            "side": "short",
            "leverage": 5,
            "positionSizePercent": 15,
            "reason": _STRUCTURED_OPEN_REASON,
        },
    )
    assert d.action == "open"
    assert d.market_context is not None
    assert d.plan is not None


# ---------------------------------------------------------------------------
# Structured dict path: close_position / partial_close_position
# ---------------------------------------------------------------------------


def test_close_position_structured_reason() -> None:
    """close_position (100%) + dict reason → close action, structured fields populated."""
    d = _parse_decision_from_tool_call(
        "close_position",
        {"symbol": "BTC", "percentage": 100, "reason": _STRUCTURED_HOLD_REASON},
    )
    assert d.action == "close"
    assert d.market_context == _STRUCTURED_HOLD_REASON["market_context"]
    assert d.structured_confidence == pytest.approx(0.45)


def test_closePosition_partial_structured_reason() -> None:
    """closePosition (<100%) + dict reason → partial_close, structured fields."""
    d = _parse_decision_from_tool_call(
        "closePosition",
        {"symbol": "ETH", "percentage": 50, "reason": _STRUCTURED_OPEN_REASON},
    )
    assert d.action == "partial_close"
    assert d.close_percentage == Decimal(50)
    assert d.market_context is not None
    assert d.gates_passed is not None
    assert len(d.gates_passed) == 2


def test_partial_close_position_structured_reason() -> None:
    """partial_close_position + dict reason → structured fields populated."""
    d = _parse_decision_from_tool_call(
        "partial_close_position",
        {"symbol": "SOL", "percentage": 30, "reason": _STRUCTURED_HOLD_REASON},
    )
    assert d.action == "partial_close"
    assert d.close_percentage == Decimal(30)
    assert d.market_context is not None


# ---------------------------------------------------------------------------
# Error path: StructuredOutputContractError (Principle 4 — loud failures)
# ---------------------------------------------------------------------------


def test_dict_reason_missing_market_context_raises() -> None:
    """dict reason missing required market_context → StructuredOutputContractError."""
    bad_reason = {k: v for k, v in _STRUCTURED_HOLD_REASON.items() if k != "market_context"}
    with pytest.raises(StructuredOutputContractError) as exc_info:
        _parse_decision_from_tool_call("hold", {"reason": bad_reason})
    assert exc_info.value.tool_name == "hold"
    assert "market_context" in exc_info.value.validation_error


def test_dict_reason_missing_justification_raises() -> None:
    """dict reason missing required justification → StructuredOutputContractError."""
    bad_reason = {k: v for k, v in _STRUCTURED_HOLD_REASON.items() if k != "justification"}
    with pytest.raises(StructuredOutputContractError):
        _parse_decision_from_tool_call("hold", {"reason": bad_reason})


def test_dict_reason_confidence_out_of_range_raises() -> None:
    """dict reason with confidence > 1.0 → StructuredOutputContractError."""
    bad_reason = {**_STRUCTURED_HOLD_REASON, "confidence": 1.5}
    with pytest.raises(StructuredOutputContractError) as exc_info:
        _parse_decision_from_tool_call("hold", {"reason": bad_reason})
    assert exc_info.value.tool_name == "hold"
    assert "confidence" in exc_info.value.validation_error


def test_dict_reason_confidence_negative_raises() -> None:
    """dict reason with confidence < 0 → StructuredOutputContractError."""
    bad_reason = {**_STRUCTURED_HOLD_REASON, "confidence": -0.1}
    with pytest.raises(StructuredOutputContractError):
        _parse_decision_from_tool_call("hold", {"reason": bad_reason})


def test_dict_reason_open_position_missing_field_raises() -> None:
    """open_position + dict reason missing required field → StructuredOutputContractError."""
    bad_reason = {k: v for k, v in _STRUCTURED_OPEN_REASON.items() if k != "invalidation_condition"}
    with pytest.raises(StructuredOutputContractError) as exc_info:
        _parse_decision_from_tool_call(
            "open_position",
            {"symbol": "BTC", "side": "long", "leverage": 10, "size": 5, "reason": bad_reason},
        )
    assert exc_info.value.tool_name == "open_position"


def test_dict_reason_close_position_contract_error() -> None:
    """close_position + malformed dict reason → StructuredOutputContractError."""
    bad_reason = {**_STRUCTURED_HOLD_REASON, "confidence": 99}
    with pytest.raises(StructuredOutputContractError) as exc_info:
        _parse_decision_from_tool_call(
            "close_position",
            {"symbol": "BTC", "percentage": 100, "reason": bad_reason},
        )
    assert exc_info.value.tool_name == "close_position"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _assert_structured_fields_none(d: Decision) -> None:
    """Assert all 6 StructuredReason-derived fields are None (legacy path)."""
    assert d.market_context is None, f"market_context should be None, got {d.market_context!r}"
    assert d.gates_passed is None, f"gates_passed should be None, got {d.gates_passed!r}"
    assert d.invalidation_condition is None, (
        f"invalidation_condition should be None, got {d.invalidation_condition!r}"
    )
    assert d.plan is None, f"plan should be None, got {d.plan!r}"
    assert d.structured_confidence is None, (
        f"structured_confidence should be None, got {d.structured_confidence!r}"
    )
    assert d.output_language is None, (
        f"output_language should be None, got {d.output_language!r}"
    )
