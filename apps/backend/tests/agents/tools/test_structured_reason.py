"""Tests for StructuredReason production schema module (Step 1, PR-B1).

Coverage:
  - Minimal valid payload for hold scenario (plan=None)
  - Minimal valid payload for non-hold scenario (plan populated)
  - ValidationError on missing required fields
  - ValidationError on out-of-range confidence
  - ValidationError on wrong type for gates_passed
  - ValidationError on invalid output_language literal
  - JSON roundtrip fidelity (dumps → loads → model_validate)
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from omnitrade.agents.tools.structured_reason import (
    STRUCTURED_REASON_JSON_SCHEMA,
    PlanBlock,
    StructuredReason,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_HOLD_PAYLOAD: dict = {
    "market_context": "BTC is trading in a tight range between 42 000 and 43 000 USDT with no clear directional bias.",
    "gates_passed": [],
    "invalidation_condition": "Daily close above 44 000 USDT would signal a breakout.",
    "plan": None,
    "confidence": 0.45,
    "justification": (
        "No strong trend or momentum signal is present.  RSI at 50 and Bollinger Bands compressed indicate "
        "a consolidation phase.  Holding is the correct decision until a clear breakout or breakdown occurs. "
        "Risk-reward on any entry here is unfavourable given the ambiguous regime."
    ),
    "output_language": "zh",
}

_VALID_OPEN_PAYLOAD: dict = {
    "market_context": (
        "BTC is in a sustained uptrend confirmed by EMA20 > EMA50 > EMA200.  RSI holding above 58 "
        "with MACD bullish crossover signals continued momentum.  Volume expansion on recent green candles "
        "supports the thesis of institutional accumulation."
    ),
    "gates_passed": [
        "EMA alignment gate: EMA20 > EMA50 > EMA200 confirms primary uptrend",
        "RSI momentum gate: RSI at 62 is above the 55 threshold for momentum confirmation",
        "MACD gate: MACD line crossed above signal line on D1 candle",
    ],
    "invalidation_condition": "Daily close below 41 500 USDT would invalidate the bullish structure.",
    "plan": {
        "entry": 43200.0,
        "stop_loss": 41500.0,
        "take_profit_1": 46000.0,
        "take_profit_2": 48500.0,
        "risk_usd": 170.0,
        "r_multiple_target": 1.65,
    },
    "confidence": 0.75,
    "justification": (
        "The triple EMA alignment on the daily timeframe is the highest-conviction trend signal we track.  "
        "RSI at 62 with no divergence shows momentum is intact.  The MACD bullish crossover on D1 adds "
        "a secondary confirmation.  Entry at 43 200 provides a 4% buffer above EMA50 support.  "
        "Stop at 41 500 is below the most recent swing low, limiting risk to approximately 1% of account.  "
        "TP1 at 46 000 targets the previous all-time high zone with 1.65R reward.  TP2 extended to 48 500 "
        "for a portion of the position if momentum continues."
    ),
    "output_language": "en",
}


# ---------------------------------------------------------------------------
# 1. Minimal valid payload — hold scenario (plan=None)
# ---------------------------------------------------------------------------


def test_hold_payload_parses_successfully() -> None:
    reason = StructuredReason.model_validate(_VALID_HOLD_PAYLOAD)
    assert reason.plan is None
    assert reason.output_language == "zh"
    assert 0.0 <= reason.confidence <= 1.0


# ---------------------------------------------------------------------------
# 2. Minimal valid payload — non-hold scenario (plan populated)
# ---------------------------------------------------------------------------


def test_open_payload_parses_successfully() -> None:
    reason = StructuredReason.model_validate(_VALID_OPEN_PAYLOAD)
    assert reason.plan is not None
    assert reason.plan.entry == 43200.0
    assert reason.plan.stop_loss == 41500.0
    assert reason.plan.take_profit_1 == 46000.0
    assert reason.plan.take_profit_2 == 48500.0
    assert reason.plan.risk_usd == 170.0
    assert reason.plan.r_multiple_target == 1.65
    assert reason.output_language == "en"


# ---------------------------------------------------------------------------
# 3. Missing market_context → ValidationError
# ---------------------------------------------------------------------------


def test_missing_market_context_raises() -> None:
    payload = {**_VALID_HOLD_PAYLOAD}
    del payload["market_context"]
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "market_context" in fields


# ---------------------------------------------------------------------------
# 4. Missing invalidation_condition → ValidationError
# ---------------------------------------------------------------------------


def test_missing_invalidation_condition_raises() -> None:
    payload = {**_VALID_HOLD_PAYLOAD}
    del payload["invalidation_condition"]
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "invalidation_condition" in fields


# ---------------------------------------------------------------------------
# 5. Missing justification → ValidationError
# ---------------------------------------------------------------------------


def test_missing_justification_raises() -> None:
    payload = {**_VALID_HOLD_PAYLOAD}
    del payload["justification"]
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "justification" in fields


# ---------------------------------------------------------------------------
# 6. confidence out of [0, 1] → ValidationError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range_raises(bad_confidence: float) -> None:
    payload = {**_VALID_HOLD_PAYLOAD, "confidence": bad_confidence}
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "confidence" in fields


# ---------------------------------------------------------------------------
# 7. gates_passed is a string instead of list → ValidationError
# ---------------------------------------------------------------------------


def test_gates_passed_string_raises() -> None:
    payload = {**_VALID_HOLD_PAYLOAD, "gates_passed": "EMA alignment gate passed"}
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "gates_passed" in fields


# ---------------------------------------------------------------------------
# 8. output_language not in {"zh", "en"} → ValidationError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_lang", ["cn", "english", "zh-CN", "", "ZH", "EN"])
def test_output_language_invalid_raises(bad_lang: str) -> None:
    payload = {**_VALID_HOLD_PAYLOAD, "output_language": bad_lang}
    with pytest.raises(ValidationError) as exc_info:
        StructuredReason.model_validate(payload)
    errors = exc_info.value.errors()
    fields = [e["loc"][0] for e in errors]
    assert "output_language" in fields


# ---------------------------------------------------------------------------
# 9. JSON roundtrip — dumps → loads → model_validate preserves fidelity
# ---------------------------------------------------------------------------


def test_json_roundtrip_hold() -> None:
    original = StructuredReason.model_validate(_VALID_HOLD_PAYLOAD)
    dumped = original.model_dump_json()
    loaded = StructuredReason.model_validate_json(dumped)
    assert loaded == original
    assert loaded.plan is None


def test_json_roundtrip_open_with_plan() -> None:
    original = StructuredReason.model_validate(_VALID_OPEN_PAYLOAD)
    dumped = original.model_dump_json()
    loaded = StructuredReason.model_validate_json(dumped)
    assert loaded == original
    assert loaded.plan is not None
    assert loaded.plan.entry == original.plan.entry
    assert loaded.plan.r_multiple_target == original.plan.r_multiple_target


def test_json_roundtrip_via_stdlib_json() -> None:
    """Verify stdlib json.dumps / json.loads path (used by DB repository layer)."""
    original = StructuredReason.model_validate(_VALID_OPEN_PAYLOAD)
    dumped_str = json.dumps(original.model_dump())
    reloaded_dict = json.loads(dumped_str)
    restored = StructuredReason.model_validate(reloaded_dict)
    assert restored == original


# ---------------------------------------------------------------------------
# 10. STRUCTURED_REASON_JSON_SCHEMA is a non-empty dict with expected keys
# ---------------------------------------------------------------------------


def test_schema_constant_is_populated() -> None:
    assert isinstance(STRUCTURED_REASON_JSON_SCHEMA, dict)
    assert "properties" in STRUCTURED_REASON_JSON_SCHEMA
    props = STRUCTURED_REASON_JSON_SCHEMA["properties"]
    expected_fields = {
        "market_context",
        "gates_passed",
        "invalidation_condition",
        "plan",
        "confidence",
        "justification",
        "output_language",
    }
    assert expected_fields.issubset(props.keys())


# ---------------------------------------------------------------------------
# 11. Default output_language is "zh" when field is omitted
# ---------------------------------------------------------------------------


def test_output_language_defaults_to_zh() -> None:
    payload = {k: v for k, v in _VALID_HOLD_PAYLOAD.items() if k != "output_language"}
    reason = StructuredReason.model_validate(payload)
    assert reason.output_language == "zh"


# ---------------------------------------------------------------------------
# 12. PlanBlock — all fields optional, empty PlanBlock validates
# ---------------------------------------------------------------------------


def test_plan_block_all_optional() -> None:
    plan = PlanBlock.model_validate({})
    assert plan.entry is None
    assert plan.stop_loss is None
    assert plan.take_profit_2 is None
