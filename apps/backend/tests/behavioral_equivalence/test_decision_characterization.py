"""Characterization driver — 22 per-fixture tests + 4 aggregate gates.

The per-fixture tests parametrize over every discovered
``(snapshot, baseline)`` pair and assert that the Python think-node
(replayed from its cassette) produces a Decision behaviourally equivalent
to the hand-curated baseline contract. The 4 aggregate tests then assert
the gates from the consensus plan §5 (overall pass-rate, per-bucket
pass-rate, population drift per action class, direction consistency).

The gate is a **characterization** gate: regression of the Python port
against the frozen hand-curated contract. See
``.omc/plans/phase-8-oracle-spike-report.md`` for the evidence chain and
``docs/ARCHITECTURE.md`` Test Strategy for the governing contract.

Implementation: all semantic logic lives in ``parity_lib``; this module
is a thin pytest wrapper that caches a single ``CharacterizationReport``
via a session-scoped fixture so we don't recompute it per test case.
"""

from __future__ import annotations

import pytest

from omnitrade.agents.think_node import _decision_from_llm_response
from tests.behavioral_equivalence.parity_lib import (
    ACTION_CLASSES,
    CLOSE_PATH_BUCKETS,
    DEFAULT_CASSETTES_DIR,
    DEFAULT_FIXTURES_DIR,
    CharacterizationReport,
    _load_json,
    compare_fixture,
    default_thresholds,
    discover_fixtures,
    load_cassette_response,
    run_characterization,
)

_PAIRS = discover_fixtures(DEFAULT_FIXTURES_DIR)
_THRESHOLDS = default_thresholds()


@pytest.fixture(scope="module")
def characterization_report() -> CharacterizationReport:
    """Run the full characterization sweep once per test session."""
    return run_characterization(
        fixtures_dir=DEFAULT_FIXTURES_DIR,
        cassettes_dir=DEFAULT_CASSETTES_DIR,
        thresholds=_THRESHOLDS,
    )


# ── per-fixture tests (22 parametrised cases) ──────────────────────────── #


@pytest.mark.characterization
@pytest.mark.parametrize("pair", _PAIRS, ids=[p.fixture_id for p in _PAIRS])
def test_fixture_characterization(pair):  # type: ignore[no-untyped-def]
    """Every fixture must satisfy action/symbol/side/leverage/size/close-path."""
    baseline = _load_json(pair.baseline_path)
    response = load_cassette_response(DEFAULT_CASSETTES_DIR / f"{pair.fixture_id}.yaml")
    decision = _decision_from_llm_response(response)
    result = compare_fixture(pair.fixture_id, baseline, decision)
    assert result.passed, (
        f"fixture {pair.fixture_id} failed characterization: " + "; ".join(result.failures)
    )


# ── aggregate gates (4 tests) ──────────────────────────────────────────── #


@pytest.mark.characterization
def test_overall_pass_rate(characterization_report: CharacterizationReport) -> None:
    """Overall pass-rate ≥ 0.95."""
    threshold = _THRESHOLDS["overall"]
    assert characterization_report.overall_pass_rate >= threshold, (
        f"overall_pass_rate={characterization_report.overall_pass_rate:.3f} < {threshold}"
    )


@pytest.mark.characterization
def test_per_bucket_pass_rate(characterization_report: CharacterizationReport) -> None:
    """Every close-path bucket with ≥1 fixture must pass ≥ 0.95."""
    threshold = _THRESHOLDS["bucket"]
    offending: list[str] = []
    for bucket in CLOSE_PATH_BUCKETS:
        stats = characterization_report.per_bucket[bucket]
        if stats["total"] > 0 and stats["pass_rate"] < threshold:
            offending.append(f"{bucket}:{stats['pass_rate']:.3f}")
    assert not offending, f"buckets below {threshold}: {offending}"


@pytest.mark.characterization
def test_population_drift(characterization_report: CharacterizationReport) -> None:
    """Per action class, |baseline_fraction − PY_fraction| ≤ 0.05."""
    threshold = _THRESHOLDS["drift"]
    offending: list[str] = []
    for cls in ACTION_CLASSES:
        drift = characterization_report.population_drift[cls]
        if drift > threshold:
            offending.append(f"{cls}:{drift:.3f}")
    assert not offending, f"drift over {threshold}: {offending}"


@pytest.mark.characterization
def test_direction_consistency(characterization_report: CharacterizationReport) -> None:
    """Long/short agreement ratio ≥ 0.95."""
    threshold = _THRESHOLDS["direction"]
    assert characterization_report.direction_consistency >= threshold, (
        f"direction_consistency={characterization_report.direction_consistency:.3f} < {threshold}"
    )
