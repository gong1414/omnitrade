"""Cassette integrity tests — Phase 4.5 deliverable.

Every Phase-0 frozen fixture MUST have a matching cassette under
``tests/behavioral_equivalence/cassettes/``. This test:

1. Asserts the set of cassettes is a superset of the 22 baseline ids.
2. Loads each cassette and round-trips it through
   ``_decision_from_llm_response`` to confirm the recorded response
   produces the *expected action* for that fixture.

Expected action mapping (per fixture's frozen ``tool_calls``):
  * AI-initiated ``openPosition``     → Decision.action == "open"
  * AI-initiated ``closePosition 100`` → Decision.action == "close"
  * AI-initiated ``closePosition <100`` → Decision.action == "partial_close"
  * AI ``hold``                        → Decision.action == "hold"
  * Monitor-only fixtures (no ai tool_calls) → Decision.action == "hold"
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.think_node import _decision_from_llm_response
from tests.behavioral_equivalence._cassette_synth import (
    CASSETTE_DIR,
    FIXTURES_DIR,
    load_baseline_fixture,
)
from tests.behavioral_equivalence.conftest import load_cassette_response

_BASELINE_PATHS = sorted(FIXTURES_DIR.glob("case_*.json"))


def _expected_action(fixture: dict[str, Any]) -> str:
    ai_calls = [c for c in (fixture.get("tool_calls") or []) if c.get("initiated_by") == "ai"]
    if not ai_calls:
        return "hold"
    tool = ai_calls[0].get("tool")
    if tool == "openPosition":
        return "open"
    if tool == "hold":
        return "hold"
    if tool == "closePosition":
        pct = (ai_calls[0].get("args") or {}).get("percentage", 100)
        return "close" if Decimal(str(pct)) >= Decimal(100) else "partial_close"
    if tool == "partialClose":
        return "partial_close"
    # Unknown tool (e.g. jury sub-agents falling through) -> hold.
    return "hold"


def test_all_22_fixtures_have_cassettes() -> None:
    """Hard count gate — exactly 22 baseline fixtures & cassettes exist."""
    assert len(_BASELINE_PATHS) == 22, (
        f"expected 22 baseline decision fixtures, found {len(_BASELINE_PATHS)}"
    )
    missing: list[str] = []
    for path in _BASELINE_PATHS:
        fixture = load_baseline_fixture(path)
        fid = fixture.get("case_id") or path.stem
        if not (CASSETTE_DIR / f"{fid}.yaml").exists():
            missing.append(str(fid))
    assert missing == [], f"missing cassettes for: {missing}"


@pytest.mark.parametrize(
    "baseline_path",
    _BASELINE_PATHS,
    ids=[p.stem for p in _BASELINE_PATHS],
)
def test_cassette_response_decodes_to_expected_action(baseline_path: Any) -> None:
    """Replay cassette → _decision_from_llm_response → action matches fixture."""
    fixture = load_baseline_fixture(baseline_path)
    fixture_id = fixture.get("case_id") or baseline_path.stem
    response = load_cassette_response(fixture_id)
    decision = _decision_from_llm_response(response)
    expected = _expected_action(fixture)
    assert decision.action == expected, (
        f"fixture={fixture_id}: expected action={expected!r}, got {decision.action!r} from cassette"
    )
