"""Characterization library — shared logic for the 22/22 behavioural gate.

This module is consumed by both the pytest driver
(``test_decision_characterization.py``) and the CLI driver
(``scripts/run_characterization.py``). The filename ``parity_lib.py`` is
preserved to minimise import churn; the **semantics** are explicitly
characterization.

Semantics — characterization
============================

The 22/22 gate locks regression against a **frozen hand-curated contract**
encoded by the 22 ``baseline_decisions/decision_NN_*.json`` files. It is
not byte-exact parity replay:

* 13 of 22 baselines are monitor-initiated closes (``trailing_stop`` /
  ``stop_loss`` / ``partial_profit``) that never invoke the LLM by design
  — there are no "raw bytes" to capture at the LLM layer.
* The 9 AI-initiated baselines carry no provenance metadata (no model-id,
  no seed, no temperature, no captured request/response envelope).
* The baseline JSONs contain human prose ``notes``, manual arithmetic, and
  explicit ``EDGE CASE`` markers — signatures of hand-authored contracts,
  not captured telemetry.
* The companion ``_cassette_synth.py`` module synthesises cassettes
  deterministically from the baseline JSONs ("pure — no network"), not
  recorded from live execution.

Gate composition
================

The gate asserts the Python think-node pipeline is behaviourally
equivalent to the hand-curated baseline contract across all 22 frozen
fixtures. "Equivalent" is defined as:

* Per-fixture: action class, symbol, side, leverage (diff 0), size (±5 %
  open / ±10 % close), and close-path class must all match.
* Aggregate: overall pass-rate ≥ 0.95, every close-path bucket ≥ 0.95,
  population drift per action class ≤ 0.05, direction consistency ≥ 0.95.

Monitor-vs-AI boundary
----------------------

Three close paths are handled *outside* the LLM loop by the monitors in
``application/monitors/``:

* ``trailing_stop`` — driven by ``trailing_stop_monitor``
* ``stop_loss``    — driven by ``stop_loss_monitor``
* ``partial_profit`` — driven by ``partial_profit_monitor``

These three paths write state directly without calling the think-node.
Each baseline ``tool_call`` therefore carries an ``initiated_by`` field
(`"ai"` or `"monitor"`); cassettes for monitor-only fixtures synthesise a
benign ``hold`` so the think-node under replay returns
``Decision(action="hold")``.

The per-fixture comparison in this module honours that boundary: when a
baseline is monitor-initiated, a Python ``hold`` is the **correct
think-node answer** — the monitor drives the actual close. Any regression
that causes the think-node to *also* try to close a monitor-handled
position would fail the cassette-integrity test first; this gate verifies
the complementary direction: the think-node does not override monitor
paths with a bogus action.

For AI-initiated baselines, the comparison is direct action-class equality.

Close-path classification mirrors the 4 buckets
``{stop_loss, trailing_stop, partial_profit, ai_decision}`` plus ``none``.
The Python side infers its close-path from the triggered Decision action
vs. the baseline's ``close_path`` field; the two must match exactly for
the bucket assertion, except that monitor-driven paths compare Python
"none" (no think-node close) against the baseline's actual bucket — the
bucket assertion then covers monitor fixtures via the handoff contract.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from omnitrade.agents.think_node import _decision_from_llm_response
from omnitrade.domain.entities import Decision

# ── paths ──────────────────────────────────────────────────────────────── #

_HERE = Path(__file__).resolve()
# apps/backend/tests/behavioral_equivalence/parity_lib.py → repo root
REPO_ROOT: Path = _HERE.parents[4]
DEFAULT_FIXTURES_DIR: Path = REPO_ROOT / "tests" / "fixtures" / "frozen"
DEFAULT_CASSETTES_DIR: Path = _HERE.parent / "cassettes"


# ── constants ──────────────────────────────────────────────────────────── #

ACTION_CLASSES: tuple[str, ...] = ("open", "close", "partial_close", "hold")
CLOSE_PATH_BUCKETS: tuple[str, ...] = (
    "stop_loss",
    "trailing_stop",
    "partial_profit",
    "ai_decision",
)

# Per-fixture tolerances from consensus plan §5 Phase 4.5.
SIZE_TOLERANCE_OPEN = Decimal("0.05")  # ±5 % for open
SIZE_TOLERANCE_CLOSE = Decimal("0.10")  # ±10 % for close / partial_close


# ── dataclasses ────────────────────────────────────────────────────────── #


@dataclass(frozen=True)
class FixturePair:
    """One (snapshot, baseline) pair resolved by matching snapshot id."""

    fixture_id: str
    snapshot_path: Path
    baseline_path: Path


@dataclass(frozen=True)
class ActionSummary:
    """Canonicalised action extracted from a tool call."""

    action: str  # ACTION_CLASSES member
    symbol: str | None
    side: str | None
    leverage: int | None
    size: Decimal | None
    close_percentage: Decimal | None


@dataclass
class FixtureResult:
    """Per-fixture outcome; ``passed`` summarises all sub-criteria."""

    fixture_id: str
    baseline_close_path: str
    baseline_initiated_by: str
    baseline_action: ActionSummary
    python_action: ActionSummary
    python_close_path: str
    passed: bool
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.fixture_id,
            "passed": self.passed,
            "baseline_close_path": self.baseline_close_path,
            "baseline_initiated_by": self.baseline_initiated_by,
            "baseline_action": _action_to_dict(self.baseline_action),
            "python_action": _action_to_dict(self.python_action),
            "python_close_path": self.python_close_path,
            "failures": list(self.failures),
        }


@dataclass
class CharacterizationReport:
    """Aggregated characterization-gate report."""

    run_at: str
    fixtures_total: int
    passed: int
    overall_pass_rate: float
    per_bucket: dict[str, dict[str, Any]]
    population_drift: dict[str, float]
    direction_consistency: float
    per_fixture: list[FixtureResult]
    thresholds: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_at": self.run_at,
            "fixtures_total": self.fixtures_total,
            "passed": self.passed,
            "overall_pass_rate": self.overall_pass_rate,
            "per_bucket": self.per_bucket,
            "population_drift": self.population_drift,
            "direction_consistency": self.direction_consistency,
            "thresholds": self.thresholds,
            "per_fixture": [r.to_dict() for r in self.per_fixture],
        }

    def all_gates_green(self) -> tuple[bool, list[str]]:
        """Return (pass, reasons) for the 4 aggregate gates."""
        reasons: list[str] = []
        ov = self.thresholds["overall"]
        bucket_thr = self.thresholds["bucket"]
        drift_thr = self.thresholds["drift"]
        direction_thr = self.thresholds["direction"]

        if self.overall_pass_rate < ov:
            reasons.append(f"overall_pass_rate={self.overall_pass_rate:.3f} < {ov}")
        for bucket, stats in self.per_bucket.items():
            if stats["total"] > 0 and stats["pass_rate"] < bucket_thr:
                reasons.append(
                    f"bucket[{bucket}].pass_rate={stats['pass_rate']:.3f} < {bucket_thr}"
                )
        for action, d in self.population_drift.items():
            if d > drift_thr:
                reasons.append(f"population_drift[{action}]={d:.3f} > {drift_thr}")
        if self.direction_consistency < direction_thr:
            reasons.append(
                f"direction_consistency={self.direction_consistency:.3f} < {direction_thr}"
            )
        return (len(reasons) == 0, reasons)


def _action_to_dict(a: ActionSummary) -> dict[str, Any]:
    return {
        "action": a.action,
        "symbol": a.symbol,
        "side": a.side,
        "leverage": a.leverage,
        "size": str(a.size) if a.size is not None else None,
        "close_percentage": str(a.close_percentage) if a.close_percentage is not None else None,
    }


# ── fixture discovery ──────────────────────────────────────────────────── #


def discover_fixtures(fixtures_dir: Path) -> list[FixturePair]:
    """Discover (snapshot_NN, decision_NN) pairs by matching trailing id suffix.

    The match key is the baseline's ``case_id`` field (which equals the
    snapshot file's ``id``). This keeps pairing robust against filename drift.
    """
    snapshot_dir = fixtures_dir / "market_snapshots"
    baseline_dir = fixtures_dir / "baseline_decisions"
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"market_snapshots not found: {snapshot_dir}")
    if not baseline_dir.exists():
        raise FileNotFoundError(f"baseline_decisions not found: {baseline_dir}")

    snapshots_by_id: dict[str, Path] = {}
    for path in sorted(snapshot_dir.glob("case_*.json")):
        data = _load_json(path)
        sid = str(data.get("id") or data.get("case_id") or path.stem)
        snapshots_by_id[sid] = path

    pairs: list[FixturePair] = []
    for path in sorted(baseline_dir.glob("case_*.json")):
        data = _load_json(path)
        sid = str(data.get("case_id") or "").strip()
        if not sid:
            raise ValueError(f"baseline missing case_id: {path}")
        if sid not in snapshots_by_id:
            raise ValueError(f"no market snapshot matches baseline case_id={sid!r}")
        pairs.append(
            FixturePair(
                fixture_id=sid,
                snapshot_path=snapshots_by_id[sid],
                baseline_path=path,
            )
        )
    return pairs


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"fixture is not a JSON object: {path}")
    return data


def load_cassette_response(cassette_path: Path) -> dict[str, Any]:
    """Parse the first response body from a vcrpy cassette YAML."""
    import yaml

    if not cassette_path.exists():
        raise FileNotFoundError(f"cassette missing: {cassette_path}")
    with cassette_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    interactions = (data or {}).get("interactions") or []
    if not interactions:
        raise ValueError(f"cassette has no interactions: {cassette_path}")
    body_str = interactions[0]["response"]["body"]["string"]
    parsed: Any = json.loads(body_str)
    if not isinstance(parsed, dict):
        raise ValueError(f"cassette body is not a JSON object: {cassette_path}")
    return parsed


# ── action classification ──────────────────────────────────────────────── #


def _pick_decision_tool_call(fixture: dict[str, Any]) -> dict[str, Any] | None:
    """Return the tool call that represents the actual trading decision.

    Frozen fixtures may carry multiple tool calls per decision (team /
    jury strategies fan out to sub-agent analysis calls before the judge
    emits its final trading action). We keep the classification aligned
    with ``_cassette_synth._pick_ai_tool_call`` so baseline and cassette
    agree on the decisive call:

      1. First tool_call whose ``tool`` is one of the primitive decision
         tools (``openPosition`` / ``closePosition`` / ``partialClose``
         / ``hold``) AND whose ``initiated_by`` is ``"ai"``.
      2. Else, first tool_call that is a primitive decision tool
         regardless of initiator (covers monitor-driven closes, which
         the baseline records with ``initiated_by="monitor"``).
      3. Else, ``None`` (all calls are analyst / jury sub-agents).
    """
    decision_tools = {"openPosition", "closePosition", "partialClose", "hold"}
    calls = fixture.get("tool_calls") or []
    for call in calls:
        if call.get("tool") in decision_tools and call.get("initiated_by") == "ai":
            return dict(call)
    for call in calls:
        if call.get("tool") in decision_tools:
            return dict(call)
    return None


def classify_baseline_action(fixture: dict[str, Any]) -> tuple[ActionSummary, str]:
    """Classify the baseline into (ActionSummary, initiated_by).

    Rules (per task spec):
      * ``closePosition`` with percentage >= 100 → ``close``
      * ``closePosition`` with percentage < 100 → ``partial_close``
      * ``partialClose``                        → ``partial_close``
      * ``openPosition``                         → ``open``
      * ``hold`` or no decision tool_call        → ``hold``
    """
    chosen = _pick_decision_tool_call(fixture)
    if chosen is None:
        return _hold_summary(), "ai"

    tool = str(chosen.get("tool") or "")
    args = chosen.get("args") or {}
    initiated_by = str(chosen.get("initiated_by") or "ai")

    if tool == "hold":
        return _hold_summary(), initiated_by
    if tool == "openPosition":
        size = _coerce_decimal(
            args.get("positionSizePercent") or args.get("size") or args.get("quantity")
        )
        return (
            ActionSummary(
                action="open",
                symbol=_coerce_str(args.get("symbol")),
                side=_coerce_str(args.get("side")),
                leverage=_coerce_int(args.get("leverage")),
                size=size,
                close_percentage=None,
            ),
            initiated_by,
        )
    if tool in {"closePosition", "partialClose"}:
        pct = _coerce_decimal(args.get("percentage"))
        if pct is None:
            pct = Decimal(100) if tool == "closePosition" else Decimal(50)
        action = "close" if pct >= Decimal(100) else "partial_close"
        if tool == "partialClose":
            action = "partial_close"
        return (
            ActionSummary(
                action=action,
                symbol=_coerce_str(args.get("symbol")),
                side=_coerce_str(args.get("side")),
                leverage=None,
                size=None,
                close_percentage=pct,
            ),
            initiated_by,
        )
    # Unknown tool — treat as hold so we don't misclassify analyst sub-agents.
    return _hold_summary(), initiated_by


def classify_python_decision(decision: Decision) -> ActionSummary:
    """Classify a Python ``Decision`` entity into the same ActionSummary shape."""
    return ActionSummary(
        action=decision.action,
        symbol=decision.symbol,
        side=decision.side,
        leverage=decision.leverage,
        size=decision.size,
        close_percentage=decision.close_percentage,
    )


def _hold_summary() -> ActionSummary:
    return ActionSummary(
        action="hold",
        symbol=None,
        side=None,
        leverage=None,
        size=None,
        close_percentage=None,
    )


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# ── close-path inference ───────────────────────────────────────────────── #


def infer_python_close_path(py: ActionSummary, baseline_close_path: str) -> str:
    """Infer the Python-side close-path bucket.

    Think-node only directly drives the ``ai_decision`` bucket. Monitor
    buckets are driven outside the LLM loop in Phase 5; during Phase 4.5
    replay the think-node outputs ``hold`` and we say the path-is-none.
    """
    if py.action in {"close", "partial_close"}:
        return "ai_decision"
    if py.action == "open":
        return "none"
    # hold: no close path driven by the think-node.
    # Baseline monitor fixtures carry their own close_path; we don't guess it
    # from the think-node output — the caller reconciles this via the
    # monitor-handoff rule in ``compare_fixture``.
    return "none"


# ── per-fixture comparison ─────────────────────────────────────────────── #


def compare_fixture(
    fixture_id: str,
    baseline: dict[str, Any],
    python_decision: Decision,
) -> FixtureResult:
    """Compute the per-fixture FixtureResult.

    Acceptance rules — all sub-criteria must hold:
      * action class exact match (with monitor-handoff carve-out: a
        monitor-initiated baseline with a non-hold close is considered
        matched if Python returns ``hold``, because monitors own that path);
      * symbol match when baseline has a symbol;
      * side match when baseline has a side;
      * leverage diff == 0 when both baseline and Python report leverage;
      * size within tolerance (open ±5 %, close/partial_close ±10 %) when
        both sides report a numeric size / percentage;
      * close-path class match exactly against the plan's 5 enum values.
    """
    baseline_close_path = str(baseline.get("close_path") or "none")
    baseline_summary, initiated_by = classify_baseline_action(baseline)
    python_summary = classify_python_decision(python_decision)
    python_close_path = infer_python_close_path(python_summary, baseline_close_path)

    failures: list[str] = []

    _check_action(failures, baseline_summary, python_summary, initiated_by)
    _check_symbol(failures, baseline_summary, python_summary, initiated_by)
    _check_side(failures, baseline_summary, python_summary, initiated_by)
    _check_leverage(failures, baseline_summary, python_summary, initiated_by)
    _check_size(failures, baseline_summary, python_summary, initiated_by)
    _check_close_path(failures, baseline_close_path, python_close_path, initiated_by)

    return FixtureResult(
        fixture_id=fixture_id,
        baseline_close_path=baseline_close_path,
        baseline_initiated_by=initiated_by,
        baseline_action=baseline_summary,
        python_action=python_summary,
        python_close_path=python_close_path,
        passed=(len(failures) == 0),
        failures=failures,
    )


def _monitor_handoff_applies(initiated_by: str, baseline_action: str) -> bool:
    """Return True if the baseline is a monitor-driven close the think-node hands off."""
    return initiated_by == "monitor" and baseline_action in {"close", "partial_close"}


def _check_action(
    failures: list[str],
    baseline: ActionSummary,
    python: ActionSummary,
    initiated_by: str,
) -> None:
    if _monitor_handoff_applies(initiated_by, baseline.action):
        if python.action != "hold":
            failures.append(f"action: monitor-handoff expects python=hold, got {python.action!r}")
        return
    if baseline.action != python.action:
        failures.append(f"action: baseline={baseline.action!r} python={python.action!r}")


def _check_symbol(
    failures: list[str],
    baseline: ActionSummary,
    python: ActionSummary,
    initiated_by: str,
) -> None:
    if _monitor_handoff_applies(initiated_by, baseline.action):
        return  # python is hold → no symbol comparison
    if baseline.symbol is None:
        return
    if baseline.symbol != python.symbol:
        failures.append(f"symbol: baseline={baseline.symbol!r} python={python.symbol!r}")


def _check_side(
    failures: list[str],
    baseline: ActionSummary,
    python: ActionSummary,
    initiated_by: str,
) -> None:
    if _monitor_handoff_applies(initiated_by, baseline.action):
        return
    if baseline.side is None or python.side is None:
        return
    if baseline.side != python.side:
        failures.append(f"side: baseline={baseline.side!r} python={python.side!r}")


def _check_leverage(
    failures: list[str],
    baseline: ActionSummary,
    python: ActionSummary,
    initiated_by: str,
) -> None:
    if _monitor_handoff_applies(initiated_by, baseline.action):
        return
    if baseline.leverage is None or python.leverage is None:
        return
    if baseline.leverage != python.leverage:
        failures.append(f"leverage: baseline={baseline.leverage} python={python.leverage} (diff>0)")


def _check_size(
    failures: list[str],
    baseline: ActionSummary,
    python: ActionSummary,
    initiated_by: str,
) -> None:
    if _monitor_handoff_applies(initiated_by, baseline.action):
        return
    # open size comparison
    if baseline.action == "open" and python.action == "open":
        _check_numeric(
            failures,
            "size",
            baseline.size,
            python.size,
            tolerance=SIZE_TOLERANCE_OPEN,
        )
    # close / partial_close percentage comparison
    if baseline.action in {"close", "partial_close"} and python.action in {
        "close",
        "partial_close",
    }:
        _check_numeric(
            failures,
            "close_percentage",
            baseline.close_percentage,
            python.close_percentage,
            tolerance=SIZE_TOLERANCE_CLOSE,
        )


def _check_numeric(
    failures: list[str],
    field_name: str,
    baseline: Decimal | None,
    python: Decimal | None,
    *,
    tolerance: Decimal,
) -> None:
    if baseline is None or python is None:
        return
    if baseline == 0:
        if python != 0:
            failures.append(f"{field_name}: baseline=0 python={python}")
        return
    diff = abs(python - baseline) / abs(baseline)
    if diff > tolerance:
        failures.append(
            f"{field_name}: baseline={baseline} python={python} diff={diff:.3%} > {tolerance:.0%}"
        )


def _check_close_path(
    failures: list[str],
    baseline_close_path: str,
    python_close_path: str,
    initiated_by: str,
) -> None:
    if initiated_by == "monitor":
        # Think-node hands off to monitor; python close-path is expected
        # to be "none" (monitor will drive it in Phase 5).
        if python_close_path != "none":
            failures.append(
                f"close_path: monitor-handoff expects python='none', got {python_close_path!r}"
            )
        return
    if baseline_close_path != python_close_path:
        failures.append(
            f"close_path: baseline={baseline_close_path!r} python={python_close_path!r}"
        )


# ── aggregation ────────────────────────────────────────────────────────── #


def aggregate_results(
    results: list[FixtureResult],
    *,
    thresholds: dict[str, float],
    run_at: str,
) -> CharacterizationReport:
    """Build a CharacterizationReport from per-fixture results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    overall = (passed / total) if total else 0.0

    per_bucket = _per_bucket(results)
    drift = _population_drift(results)
    direction = _direction_consistency(results)

    return CharacterizationReport(
        run_at=run_at,
        fixtures_total=total,
        passed=passed,
        overall_pass_rate=overall,
        per_bucket=per_bucket,
        population_drift=drift,
        direction_consistency=direction,
        per_fixture=results,
        thresholds=thresholds,
    )


def _per_bucket(results: list[FixtureResult]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {
        b: {"total": 0, "passed": 0, "pass_rate": 0.0, "fixture_ids": []}
        for b in CLOSE_PATH_BUCKETS
    }
    for r in results:
        bucket = r.baseline_close_path if r.baseline_close_path in CLOSE_PATH_BUCKETS else None
        if bucket is None:
            continue
        buckets[bucket]["total"] = int(buckets[bucket]["total"]) + 1
        ids = buckets[bucket]["fixture_ids"]
        if isinstance(ids, list):
            ids.append(r.fixture_id)
        if r.passed:
            buckets[bucket]["passed"] = int(buckets[bucket]["passed"]) + 1
    for b in buckets.values():
        total = int(b["total"])
        passed = int(b["passed"])
        b["pass_rate"] = (passed / total) if total else 1.0
    return buckets


def _population_drift(results: list[FixtureResult]) -> dict[str, float]:
    """Per action-class ``|TS_fraction − PY_fraction|`` population drift.

    Measured over fixtures where the think-node *owns* the decision —
    monitor-handoff fixtures are excluded from both numerators because
    by design the think-node emits ``hold`` (the monitor drives the
    actual close in Phase 5). Including them would inflate drift by a
    constant rooted in the Phase 4 / Phase 5 boundary, not in any
    behavioural regression the gate is meant to catch.
    """
    eligible = [
        r
        for r in results
        if not _monitor_handoff_applies(r.baseline_initiated_by, r.baseline_action.action)
    ]
    total = len(eligible) or 1
    drift: dict[str, float] = {}
    for cls in ACTION_CLASSES:
        ts_fraction = sum(1 for r in eligible if r.baseline_action.action == cls) / total
        py_fraction = sum(1 for r in eligible if r.python_action.action == cls) / total
        drift[cls] = abs(ts_fraction - py_fraction)
    return drift


def _direction_consistency(results: list[FixtureResult]) -> float:
    """Long/short agreement ratio across fixtures that have a baseline side.

    Monitor-handoff fixtures (python=hold, baseline=close) are excluded from
    the denominator — there is no direction to compare when the think-node
    defers to the monitor.
    """
    eligible = [
        r
        for r in results
        if r.baseline_action.side is not None
        and not _monitor_handoff_applies(r.baseline_initiated_by, r.baseline_action.action)
    ]
    if not eligible:
        return 1.0
    agree = 0
    for r in eligible:
        if r.python_action.side is None:
            # Python didn't output a side (e.g. hold) — count as disagree only
            # when baseline explicitly required one and was not a handoff.
            continue
        if r.python_action.side == r.baseline_action.side:
            agree += 1
    return agree / len(eligible)


# ── driver: one-shot characterization run ──────────────────────────────── #


def run_characterization(
    *,
    fixtures_dir: Path = DEFAULT_FIXTURES_DIR,
    cassettes_dir: Path = DEFAULT_CASSETTES_DIR,
    thresholds: dict[str, float] | None = None,
    run_at: str | None = None,
) -> CharacterizationReport:
    """Execute the full characterization sweep and return the report.

    The "Python decision" for each fixture is produced by parsing the
    cassette response with ``_decision_from_llm_response`` — the same
    contract the think-node uses in production at the LLM boundary. This
    keeps the characterization gate framework-free: no LangGraph / vcrpy
    transport is required to compute the result deterministically.
    """
    from datetime import UTC, datetime

    if thresholds is None:
        thresholds = default_thresholds()
    if run_at is None:
        run_at = datetime.now(tz=UTC).isoformat()

    pairs = discover_fixtures(fixtures_dir)
    results: list[FixtureResult] = []
    for pair in pairs:
        baseline = _load_json(pair.baseline_path)
        cassette = cassettes_dir / f"{pair.fixture_id}.yaml"
        response = load_cassette_response(cassette)
        decision = _decision_from_llm_response(response)
        results.append(compare_fixture(pair.fixture_id, baseline, decision))

    return aggregate_results(results, thresholds=thresholds, run_at=run_at)


def default_thresholds(*, overall: float = 0.95) -> dict[str, float]:
    """Canonical characterization-gate thresholds from the consensus plan."""
    return {
        "overall": overall,
        "bucket": 0.95,
        "drift": 0.05,
        "direction": 0.95,
    }


# ── back-compat aliases ────────────────────────────────────────────────── #
# Keep the old ``ParityReport`` / ``run_parity`` names importable so existing
# call sites (and any out-of-tree tooling) continue to resolve. The names
# resolve to the characterization implementations; no behaviour change.
ParityReport = CharacterizationReport
run_parity = run_characterization


def iter_fixture_ids(fixtures_dir: Path = DEFAULT_FIXTURES_DIR) -> Iterable[str]:
    """Yield the canonical 22 fixture ids in sorted order."""
    for pair in discover_fixtures(fixtures_dir):
        yield pair.fixture_id


__all__ = [
    "ACTION_CLASSES",
    "CLOSE_PATH_BUCKETS",
    "DEFAULT_CASSETTES_DIR",
    "DEFAULT_FIXTURES_DIR",
    "REPO_ROOT",
    "SIZE_TOLERANCE_CLOSE",
    "SIZE_TOLERANCE_OPEN",
    "ActionSummary",
    "CharacterizationReport",
    "FixturePair",
    "FixtureResult",
    "ParityReport",  # back-compat alias
    "aggregate_results",
    "classify_baseline_action",
    "classify_python_decision",
    "compare_fixture",
    "default_thresholds",
    "discover_fixtures",
    "infer_python_close_path",
    "iter_fixture_ids",
    "load_cassette_response",
    "run_characterization",
    "run_parity",  # back-compat alias
]
