"""Tests for dual-path _parse_reason contract behaviour (Step 7, PR-B1).

These tests exercise the contract of the _parse_reason helper directly —
no live LLM calls, no external dependencies.

Coverage:
  - str input → returns (flat_string, None) — legacy path
  - valid dict StructuredReason → returns (justification, StructuredReason)
  - dict missing market_context → StructuredOutputContractError (loud failure)
  - dict confidence=1.5 → StructuredOutputContractError
  - dict gates_passed=None → StructuredOutputContractError
  - dict output_language="fr" → StructuredOutputContractError
  - empty dict → StructuredOutputContractError
  - dict plan.entry="abc" (non-numeric) → StructuredOutputContractError
  - dict plan=None + all other fields valid (hold) → OK, structured.plan is None
"""

from __future__ import annotations

import pytest

from omnitrade.agents.errors import StructuredOutputContractError
from omnitrade.agents.think_node import _parse_reason
from omnitrade.agents.tools.structured_reason import StructuredReason

# ---------------------------------------------------------------------------
# Shared base payload — all required fields present and valid.
# ---------------------------------------------------------------------------

_BASE_VALID: dict = {
    "market_context": "BTC is in a sustained uptrend with EMA alignment confirming momentum.",
    "gates_passed": ["EMA alignment gate: EMA20 > EMA50 > EMA200"],
    "invalidation_condition": "Daily close below 42000 USDT invalidates bullish bias.",
    "plan": None,
    "confidence": 0.72,
    "justification": (
        "Strong momentum with RSI above 55 and EMA alignment intact. "
        "Volume confirms the move. Risk-reward is favourable at current levels. "
        "No conflicting signals from the higher timeframe. "
        "This justification exceeds the 200-character quality floor."
    ),
    "output_language": "zh",
}


def _valid(**overrides: object) -> dict:
    return {**_BASE_VALID, **overrides}


# ---------------------------------------------------------------------------
# Legacy flat-string path
# ---------------------------------------------------------------------------


def test_str_input_returns_legacy_path() -> None:
    reasoning, structured = _parse_reason("hold", {"reason": "no clear signal"})
    assert reasoning == "no clear signal"
    assert structured is None


def test_str_input_empty_string_returns_legacy_path() -> None:
    reasoning, structured = _parse_reason("hold", {"reason": ""})
    assert reasoning == ""
    assert structured is None


def test_missing_reason_key_returns_empty_string_legacy() -> None:
    """args without 'reason' key: raw_reason defaults to '' (str), legacy path."""
    reasoning, structured = _parse_reason("hold", {})
    assert reasoning == ""
    assert structured is None


# ---------------------------------------------------------------------------
# Structured dict — happy path
# ---------------------------------------------------------------------------


def test_valid_dict_returns_structured_reason() -> None:
    payload = _valid()
    reasoning, structured = _parse_reason("hold", {"reason": payload})
    assert structured is not None
    assert isinstance(structured, StructuredReason)
    assert reasoning == structured.justification


def test_hold_with_plan_none_ok() -> None:
    """plan=None with all other fields valid is the canonical hold scenario."""
    payload = _valid(plan=None)
    _, structured = _parse_reason("hold", {"reason": payload})
    assert structured is not None
    assert structured.plan is None


# ---------------------------------------------------------------------------
# Structured dict — validation failures (loud, no opt-out)
# ---------------------------------------------------------------------------


def test_missing_market_context_raises_contract_error() -> None:
    payload = _valid()
    del payload["market_context"]
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("open_position", {"reason": payload})


def test_confidence_above_range_raises_contract_error() -> None:
    payload = _valid(confidence=1.5)
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("open_position", {"reason": payload})


def test_confidence_below_range_raises_contract_error() -> None:
    payload = _valid(confidence=-0.1)
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("open_position", {"reason": payload})


def test_gates_passed_null_raises_contract_error() -> None:
    payload = _valid(gates_passed=None)
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("open_position", {"reason": payload})


def test_invalid_output_language_raises_contract_error() -> None:
    payload = _valid(output_language="fr")
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("hold", {"reason": payload})


def test_empty_dict_raises_contract_error() -> None:
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("hold", {"reason": {}})


def test_plan_entry_non_numeric_raises_contract_error() -> None:
    plan_payload = {
        "entry": "abc",
        "stop_loss": 41000.0,
        "take_profit_1": 45000.0,
        "take_profit_2": None,
        "risk_usd": 100.0,
        "r_multiple_target": 2.0,
    }
    payload = _valid(plan=plan_payload)
    with pytest.raises(StructuredOutputContractError):
        _parse_reason("open_position", {"reason": payload})


def test_contract_error_contains_tool_name() -> None:
    payload = _valid()
    del payload["market_context"]
    with pytest.raises(StructuredOutputContractError) as exc_info:
        _parse_reason("my_tool", {"reason": payload})
    assert exc_info.value.tool_name == "my_tool"
