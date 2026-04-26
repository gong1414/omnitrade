"""AccuracyEval (LLM-as-judge) coverage for CLAUDE.md Gate G2.

T8 (Agno migration follow-up): Gate G2 in ``CLAUDE.md`` is currently a
shell+jq routine that the human runs by hand against the latest decision
JSON to confirm the structured-reasoning fields (``market_context`` /
``gates_passed`` / ``invalidation_condition`` / ``plan`` /
``structured_confidence`` / ``justification`` / ``output_language``)
are populated and *substantive* — not tautological boilerplate, not
``["ok"]``, not the "system has issues" fault-string the LLM emits when
it spots upstream data corruption.

``agno.eval.accuracy.AccuracyEval`` is the Agno-native upgrade.  It
orchestrates an LLM judge that scores 1-10 against an
``expected_output`` plus optional ``additional_guidelines``.  The judge
agent's response schema is :class:`AccuracyAgentResponse` (fields
``accuracy_score`` int 1-10 + ``accuracy_reason`` str).

Test strategy (deliberately deterministic, CI-safe)
---------------------------------------------------

1.  We construct fully-formed :class:`StructuredReason` payloads that
    represent (a) a *good* decision satisfying every G2 quality floor
    and (b) a *bad* decision that intentionally trips every G2 gate
    (empty justification, ``gates_passed=["ok"]``, tautological
    invalidation, etc.).

2.  We feed each payload to ``AccuracyEval.run_with_output`` — the
    Agno-native entry point that *skips* generating an answer with an
    Agent and runs only the judging step against the ``output`` string
    we provide.

3.  We swap the judge's ``evaluator_agent`` for a ``MagicMock`` whose
    ``run()`` method returns a synthesised :class:`AccuracyAgentResponse`
    so the test makes **zero** network calls.  The mock asserts that
    the rendered ``evaluation_input`` (passed positionally to
    ``evaluator_agent.run``) actually contains the G2 problem signals
    — i.e. for the bad case the judge prompt surfaces ``["ok"]``,
    empty ``justification``, etc.

4.  ``telemetry=False`` is set on every eval — Agno's analytics ping
    fails on locked-down CI runners (this caught us in T7).

5.  ``additional_guidelines`` carry the G2 evaluation rubric verbatim
    so future regression tests on the rubric itself fail loudly.

Acceptance criteria (replaces CLAUDE.md G2 jq checks)
-----------------------------------------------------
Real cycles whose ``StructuredReason`` populates every G2 quality floor
should score >= 7/10; outputs that intentionally trip the floors should
score < 5/10.  Both branches are exercised here with mocked judge
scores, plus the `additional_guidelines` rendered into the judge's
system prompt are asserted to contain every G2 rule (so silently
deleting a rule is a test failure).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.eval.accuracy import (
    AccuracyAgentResponse,
    AccuracyEval,
    AccuracyResult,
)

from omnitrade.agents.tools.structured_reason import PlanBlock, StructuredReason

pytestmark = pytest.mark.eval


# ---------------------------------------------------------------------------
# G2 evaluation rubric (CLAUDE.md verbatim, distilled into judge guidelines).
# Kept as a module-level constant so the assertion-on-rubric test below can
# verify every rule survives into the rendered evaluator-agent description.
# ---------------------------------------------------------------------------

G2_GUIDELINES: list[str] = [
    "market_context must describe current market conditions in 2-4 sentences "
    "(>= 100 chars), not just restate input numbers.",
    "gates_passed must contain at least one substantive entry (each >= 5 chars). "
    'A list like ["ok"] is BAD — gate entries should be of the form '
    "'<Gate name>: <evidence>'.",
    "invalidation_condition must be specific and testable (>= 20 chars). "
    "Tautologies like 'market goes the wrong way' or 'price moves against us' "
    "are BAD.",
    "If action is open/partial_close, plan must populate non-zero entry, "
    "stop_loss, and take_profit_1. If action is hold, plan must be null.",
    "confidence must be a calibrated float in [0.0, 1.0] — not 0.0, not NaN, "
    "and not always pinned at 0.95.",
    "justification must be a substantive chain-of-thought (>= 200 chars) — "
    "explain why the setup qualifies, which indicators contributed, and why "
    "alternatives were rejected.",
    "output_language must be either 'zh' or 'en' and must match the requested "
    "language.",
    "If the agent's reasoning text contains '异常', '错误', 'system issue', "
    "or similar fault-strings, that is a BUG REPORT — score it as a quality "
    "failure even if the structural fields are populated.",
]

G2_EXPECTED_OUTPUT: str = (
    "A trading decision whose StructuredReason payload populates every G2 "
    "quality floor: rich market_context (>=100 chars, interpretive not "
    "verbatim), >=1 substantive gates_passed entry, specific testable "
    "invalidation_condition (>=20 chars), plan present iff action is not "
    "hold, calibrated confidence in [0,1], substantive justification "
    "(>=200 chars), and output_language matching the requested language. "
    "No fault-strings ('异常' / '错误' / 'system issue') in any field."
)


# ---------------------------------------------------------------------------
# Helpers — synthesise good and bad StructuredReason payloads for the judge
# to score.  These mirror the shape /api/v1/decisions returns to the
# dashboard, and are the same shape CLAUDE.md G2 jq currently inspects.
# ---------------------------------------------------------------------------


def _good_decision() -> StructuredReason:
    """Synthesise a "high quality" decision satisfying every G2 floor."""
    return StructuredReason(
        market_context=(
            "BTC is in a sustained uptrend with EMA20 > EMA50 > EMA200 and "
            "RSI holding above 55, suggesting continuation momentum. "
            "Volume on the latest impulse leg is above the 20-bar average, "
            "and funding remains neutral so the move is not over-leveraged. "
            "ETH is lagging slightly but tracking the same regime."
        ),
        gates_passed=[
            "EMA alignment gate: EMA20 > EMA50 > EMA200 confirms primary uptrend",
            "Momentum gate: RSI=58 above neutral threshold without being overbought",
            "Volume gate: latest impulse volume = 1.4x 20-bar average",
        ],
        invalidation_condition=(
            "Daily close below 42 000 USDT would invalidate the bullish bias "
            "and force a reassessment of the regime."
        ),
        plan=PlanBlock(
            entry=43_500.0,
            stop_loss=42_000.0,
            take_profit_1=46_500.0,
            take_profit_2=48_000.0,
            risk_usd=150.0,
            r_multiple_target=2.0,
        ),
        confidence=0.72,
        justification=(
            "The setup qualifies because EMA alignment, momentum, and volume "
            "are all in agreement on the daily timeframe. Entry at 43 500 USDT "
            "is just above the prior swing high, which has flipped from "
            "resistance to support on the last retest. Stop-loss at 42 000 "
            "sits below the most recent higher-low and the EMA50, giving the "
            "trade room to breathe without invalidating structure. TP1 at "
            "46 500 represents a 2R reward and aligns with the next major "
            "supply zone visible on the weekly chart. We rejected a short "
            "fade entry because RSI and EMA stacking offer no bearish "
            "divergence yet — the asymmetry favours a long with a defined "
            "invalidation."
        ),
        output_language="en",
    )


def _bad_decision() -> StructuredReason:
    """Synthesise a "low quality" decision that intentionally trips G2.

    NOTE: ``StructuredReason`` enforces ``min_length=1`` on most string
    fields (so an *empty* justification is impossible to construct via
    the model).  We trip the *content* gates (tautology, ``["ok"]``,
    1-char justification) instead — exactly the failure modes G2 was
    written to catch on real LLM output.
    """
    return StructuredReason(
        market_context="ok",  # min_length=1 satisfied; content gate (>=100) tripped
        gates_passed=["ok"],  # the canonical CLAUDE.md G2 anti-pattern
        invalidation_condition="market goes the wrong way",  # tautology
        plan=None,
        confidence=0.0,
        justification=".",  # 1 char; floor is 200
        output_language="zh",
    )


def _serialise(reason: StructuredReason) -> str:
    """Serialise a StructuredReason exactly the way /api/v1/decisions does.

    The judge sees the same JSON the dashboard would render — so a
    high-scoring eval here means a high-quality decision in the UI.
    """
    return json.dumps(reason.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _make_eval(*, name: str) -> AccuracyEval:
    """Build an ``AccuracyEval`` configured for G2.

    No ``model`` / ``agent`` is supplied: ``run_with_output`` does not
    need either when we hand the judge a pre-mocked evaluator agent.
    """
    return AccuracyEval(
        name=name,
        input=(
            "Score this trading decision against the OmniTrade G2 quality "
            "rubric (CLAUDE.md). The decision is the JSON payload below."
        ),
        expected_output=G2_EXPECTED_OUTPUT,
        additional_guidelines=G2_GUIDELINES,
        telemetry=False,
    )


def _mock_evaluator(*, score: int, reason: str) -> MagicMock:
    """Return a MagicMock that mimics ``evaluator_agent.run(...)``.

    Agno's ``AccuracyEval.evaluate_answer`` calls
    ``evaluator_agent.run(evaluation_input, stream=False)`` and reads
    ``.content`` (must be an :class:`AccuracyAgentResponse`) plus
    ``.metrics``.  We give it both.
    """
    fake_response = MagicMock()
    fake_response.content = AccuracyAgentResponse(
        accuracy_score=score,
        accuracy_reason=reason,
    )
    fake_response.metrics = None

    evaluator = MagicMock()
    evaluator.run.return_value = fake_response
    return evaluator


# ---------------------------------------------------------------------------
# (1) Smoke — the StructuredReason fixtures themselves are valid pydantic
#     models. If this fails the rest is meaningless.
# ---------------------------------------------------------------------------


def test_structured_reason_fixtures_are_valid() -> None:
    good = _good_decision()
    assert len(good.market_context) >= 100
    assert len(good.gates_passed) >= 1
    assert all(len(g) >= 5 for g in good.gates_passed)
    assert len(good.invalidation_condition) >= 20
    assert good.plan is not None and good.plan.entry == 43_500.0
    assert 0.0 <= good.confidence <= 1.0
    assert len(good.justification) >= 200

    bad = _bad_decision()
    # Confirm the bad fixture trips the *content* (not pydantic) floors:
    assert len(bad.market_context) < 100
    assert bad.gates_passed == ["ok"]
    assert "wrong way" in bad.invalidation_condition  # tautology marker
    assert bad.plan is None
    assert bad.confidence == 0.0
    assert len(bad.justification) < 200


# ---------------------------------------------------------------------------
# (2) Construction contract — AccuracyEval was built with the right G2
#     rubric. If a future refactor silently drops a rule from
#     G2_GUIDELINES this test fails before any judging happens.
# ---------------------------------------------------------------------------


def test_accuracy_eval_carries_full_g2_rubric() -> None:
    evaluation = _make_eval(name="g2-rubric-shape")

    assert evaluation.additional_guidelines is G2_GUIDELINES
    assert evaluation.telemetry is False
    assert evaluation.expected_output == G2_EXPECTED_OUTPUT

    # Each rule must appear verbatim in the evaluator agent's
    # rendered description — proves the judge actually receives them.
    evaluator = evaluation.get_evaluator_agent()
    description = evaluator.description or ""
    for rule in G2_GUIDELINES:
        assert rule in description, f"G2 guideline missing from judge prompt: {rule!r}"


# ---------------------------------------------------------------------------
# (3) Good decision -> judge scores >= 7/10. We mock the judge so the
#     test never makes a network call; the assertion proves AccuracyEval
#     wires the score through to the result correctly.
# ---------------------------------------------------------------------------


def test_good_decision_scores_high(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = _good_decision()
    payload = _serialise(decision)

    evaluator_mock = _mock_evaluator(
        score=9,
        reason=(
            "All G2 floors satisfied: market_context is interpretive and >100 "
            "chars, gates_passed has 3 substantive entries, invalidation is "
            "specific, plan is fully populated for an open trade, confidence "
            "is calibrated, justification is multi-paragraph chain-of-thought."
        ),
    )

    evaluation = _make_eval(name="g2-good")
    monkeypatch.setattr(evaluation, "get_evaluator_agent", lambda: evaluator_mock)

    result: AccuracyResult | None = evaluation.run_with_output(
        output=payload,
        print_summary=False,
        print_results=False,
    )

    assert result is not None
    assert len(result.results) == 1
    assert result.avg_score >= 7, f"good decision must score >=7, got {result.avg_score}"

    # Single judge round-trip happened.
    assert evaluator_mock.run.call_count == 1

    # The judge prompt must contain the full StructuredReason JSON we passed.
    rendered_prompt: str = evaluator_mock.run.call_args.args[0]
    assert "EMA alignment gate" in rendered_prompt
    assert '"confidence": 0.72' in rendered_prompt
    assert "<expected_output>" in rendered_prompt
    assert "<agent_output>" in rendered_prompt


# ---------------------------------------------------------------------------
# (4) Bad decision -> judge scores < 5/10 AND the rendered prompt actually
#     surfaces every G2 problem we put into the fixture. Two assertions
#     for the price of one — score wired through + the raw signals
#     (`["ok"]`, tautology, 1-char justification) reach the judge.
# ---------------------------------------------------------------------------


def test_bad_decision_scores_low_and_judge_sees_every_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = _bad_decision()
    payload = _serialise(decision)

    evaluator_mock = _mock_evaluator(
        score=2,
        reason=(
            "G2 failures: market_context is 2 chars (floor 100), gates_passed "
            "is ['ok'] (CLAUDE.md anti-pattern), invalidation is a tautology, "
            "justification is 1 char (floor 200)."
        ),
    )

    evaluation = _make_eval(name="g2-bad")
    monkeypatch.setattr(evaluation, "get_evaluator_agent", lambda: evaluator_mock)

    result = evaluation.run_with_output(
        output=payload,
        print_summary=False,
        print_results=False,
    )

    assert result is not None
    assert len(result.results) == 1
    assert result.avg_score < 5, f"bad decision must score <5, got {result.avg_score}"

    # The whole point: assert the judge prompt surfaces every G2 problem
    # signal we put into the fixture. If a refactor stops sending the
    # output JSON to the judge, this test catches it before a real run.
    rendered_prompt: str = evaluator_mock.run.call_args.args[0]
    assert '"gates_passed"' in rendered_prompt
    assert '"ok"' in rendered_prompt  # canonical anti-pattern
    assert "market goes the wrong way" in rendered_prompt  # tautology
    assert '"justification": "."' in rendered_prompt  # 1-char justification
    assert '"confidence": 0.0' in rendered_prompt


# ---------------------------------------------------------------------------
# (5) Negative control — when AccuracyEval can't get a structured
#     response back from the judge, ``run_with_output`` returns a result
#     with no entries (it logs the error and continues). Confirm we
#     catch that silent-failure mode rather than blow up.
# ---------------------------------------------------------------------------


def test_judge_returning_invalid_payload_is_handled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = _good_decision()
    payload = _serialise(decision)

    bad_response = MagicMock()
    bad_response.content = "this is not an AccuracyAgentResponse"
    bad_response.metrics = None
    evaluator = MagicMock()
    evaluator.run.return_value = bad_response

    evaluation = _make_eval(name="g2-judge-broken")
    monkeypatch.setattr(evaluation, "get_evaluator_agent", lambda: evaluator)

    result = evaluation.run_with_output(
        output=payload,
        print_summary=False,
        print_results=False,
    )

    # AccuracyEval.evaluate_answer swallows the EvalError and logs it,
    # so we end up with a result that simply has zero entries.
    assert result is not None
    assert result.results == []


# ---------------------------------------------------------------------------
# (6) Serialised payload contract — the JSON payload the judge sees is
#     byte-for-byte the same shape /api/v1/decisions returns. Catches a
#     subtle drift where, e.g., model_dump(mode="json") starts emitting
#     PlanBlock as a non-dict.
# ---------------------------------------------------------------------------


def test_serialised_payload_matches_api_shape() -> None:
    payload = _serialise(_good_decision())
    parsed: dict[str, Any] = json.loads(payload)

    # Every G2 field present + correctly typed.
    assert isinstance(parsed["market_context"], str)
    assert isinstance(parsed["gates_passed"], list)
    assert isinstance(parsed["invalidation_condition"], str)
    assert isinstance(parsed["plan"], dict)
    assert isinstance(parsed["confidence"], float)
    assert isinstance(parsed["justification"], str)
    assert parsed["output_language"] in {"zh", "en"}

    # Plan block round-trips into its keyed shape.
    assert parsed["plan"]["entry"] == 43_500.0
    assert parsed["plan"]["stop_loss"] == 42_000.0
    assert parsed["plan"]["take_profit_1"] == 46_500.0


# ---------------------------------------------------------------------------
# (7) Cassette-gated live judge — SKIPPED on day one. Mirrors the T7
#     pattern: a single cassette under tests/eval/cassettes/accuracy_g2/
#     replays a real DeepSeek-as-judge call so the eval can be exercised
#     end-to-end without touching the network on every CI run.
# ---------------------------------------------------------------------------


_CASSETTE_DIR = Path(__file__).resolve().parent / "cassettes" / "accuracy_g2"
_CASSETTE_PATH = _CASSETTE_DIR / "live_judge_g2.yaml"


@pytest.mark.live
@pytest.mark.skipif(
    not _CASSETTE_PATH.exists(),
    reason=(
        "Live AccuracyEval cassette not recorded yet; record with "
        "`LLM_API_KEY=... uv run pytest tests/eval/ -v -m \"eval and live\" "
        "--record-mode=once`. See test docstring for details."
    ),
)
def test_live_judge_scores_good_decision_high() -> None:  # pragma: no cover - cassette-gated
    """End-to-end: real DeepSeek judge + recorded cassette + good decision.

    Day-one CI doesn't have the cassette so this test is *skipped*. To
    record:

    .. code-block:: bash

       cd apps/backend
       LLM_API_KEY=$LLM_API_KEY uv run pytest tests/eval/ -v \\
           -m "eval and live" --record-mode=once

    After recording, commit the YAML and the test will replay
    deterministically on every CI run, asserting the rubric+payload
    actually score >=7/10 against a real LLM judge.
    """
    from agno.models.deepseek import DeepSeek

    from omnitrade.backtest.cassette import cassette_context

    decision = _good_decision()
    payload = _serialise(decision)

    evaluation = AccuracyEval(
        name="g2-live-judge",
        input="Score this trading decision against CLAUDE.md G2 quality rubric.",
        expected_output=G2_EXPECTED_OUTPUT,
        additional_guidelines=G2_GUIDELINES,
        model=DeepSeek(id="deepseek-reasoner"),
        telemetry=False,
    )

    with cassette_context(_CASSETTE_PATH, mode="once"):
        result = evaluation.run_with_output(
            output=payload,
            print_summary=False,
            print_results=False,
        )

    assert result is not None
    assert result.avg_score >= 7, (
        f"live judge scored a known-good decision below G2 threshold: "
        f"{result.avg_score}/10 ({result.results[0].reason if result.results else 'no result'})"
    )
