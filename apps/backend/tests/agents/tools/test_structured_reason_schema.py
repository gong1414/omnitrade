"""Tests for STRUCTURED_REASON_JSON_SCHEMA structural contract (Step 7, PR-B1).

Coverage:
  - Schema is a dict with 'properties' and 'required' keys
  - 'properties' contains all 6 required fields + 1 optional (plan) = 7 keys
  - 'required' list contains the 6 mandatory fields
  - 'plan' is NOT in 'required' (hold scenario)
  - Schema round-trips through json.dumps / json.loads
  - 'gates_passed' declares type=array, items.type=string
  - 'confidence' declares type=number, minimum=0.0, maximum=1.0
  - 'output_language' declares enum=["zh","en"]
"""

from __future__ import annotations

import json

from omnitrade.agents.tools.structured_reason import STRUCTURED_REASON_JSON_SCHEMA

_SCHEMA = STRUCTURED_REASON_JSON_SCHEMA

# Fields pydantic marks as required (no default, no default_factory).
# gates_passed has default_factory=list and output_language has default="zh",
# so pydantic does NOT include them in 'required'.
_REQUIRED_FIELDS = {
    "market_context",
    "invalidation_condition",
    "justification",
    "confidence",
}

_ALL_FIELDS = {
    "market_context",
    "gates_passed",
    "invalidation_condition",
    "plan",
    "confidence",
    "justification",
    "output_language",
}


def test_schema_is_dict() -> None:
    assert isinstance(_SCHEMA, dict)


def test_schema_has_properties_key() -> None:
    assert "properties" in _SCHEMA


def test_schema_has_required_key() -> None:
    assert "required" in _SCHEMA


def test_properties_contains_all_seven_fields() -> None:
    props = _SCHEMA["properties"]
    assert isinstance(props, dict)
    assert _ALL_FIELDS.issubset(set(props.keys()))


def test_required_contains_four_mandatory_fields() -> None:
    """Fields without defaults are in required; fields with default/default_factory are not."""
    required_set = set(_SCHEMA["required"])
    assert _REQUIRED_FIELDS.issubset(required_set)


def test_plan_not_in_required() -> None:
    """plan is optional — hold decisions carry plan=None."""
    assert "plan" not in _SCHEMA["required"]


def test_schema_round_trips_json() -> None:
    serialised = json.dumps(_SCHEMA)
    restored = json.loads(serialised)
    assert restored == _SCHEMA


def test_gates_passed_schema_is_array_of_strings() -> None:
    """gates_passed uses default_factory=list; pydantic emits it as a plain array schema."""
    gp = _SCHEMA["properties"]["gates_passed"]
    # Pydantic v2 may wrap in anyOf for fields with defaults; unwrap if needed.
    if "anyOf" in gp:
        array_variant = next((v for v in gp["anyOf"] if v.get("type") == "array"), None)
        assert array_variant is not None, f"No array variant in anyOf: {gp}"
        gp = array_variant
    assert gp.get("type") == "array", f"Expected type=array, got: {gp}"
    items = gp.get("items", {})
    assert items.get("type") == "string", f"Expected items.type=string, got: {items}"


def test_confidence_schema_number_with_bounds() -> None:
    conf = _SCHEMA["properties"]["confidence"]
    assert conf.get("type") == "number", f"Expected type=number, got: {conf}"
    assert conf.get("minimum") == 0.0, f"Expected minimum=0.0, got: {conf}"
    assert conf.get("maximum") == 1.0, f"Expected maximum=1.0, got: {conf}"


def test_output_language_schema_enum() -> None:
    """output_language has default='zh'; pydantic may or may not wrap in anyOf."""
    ol = _SCHEMA["properties"]["output_language"]
    # Pydantic v2 may wrap in anyOf for fields with defaults; unwrap if needed.
    if "anyOf" in ol:
        enum_variant = next((v for v in ol["anyOf"] if "enum" in v), None)
        assert enum_variant is not None, f"No enum variant in anyOf: {ol}"
        ol = enum_variant
    assert "enum" in ol, f"Expected enum key, got: {ol}"
    assert set(ol["enum"]) == {"zh", "en"}, f"Expected enum=['zh','en'], got: {ol['enum']}"
