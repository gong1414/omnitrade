"""Characterization CLI driver.

The gate asserts the Python think-node reproduces the hand-curated
baseline contract across 22 frozen fixtures. See
``.omc/plans/phase-8-oracle-spike-report.md`` for the evidence chain and
``docs/ARCHITECTURE.md`` Test Strategy for the governing contract.

Usage::

    python scripts/run_characterization.py \
        --fixtures tests/fixtures/frozen/ \
        --cassettes apps/backend/tests/behavioral_equivalence/cassettes/ \
        --threshold 0.95 \
        --report apps/backend/tests/behavioral_equivalence/reports/YYYY-MM-DD.json

Exit codes
==========
``0`` — all four aggregate gates green (overall ≥ threshold, every bucket
≥ 0.95, every action-class drift ≤ 0.05, direction consistency ≥ 0.95).
``1`` — any gate fails; stderr lists the offending gates.
``2`` — configuration / IO error (bad path, unreadable fixture).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make the behavioral_equivalence package importable so we can share parity_lib
# with the pytest driver. The script is deliberately `uv --project apps/backend run`
# aware so it resolves apps/backend/tests on the Python path via pyproject.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[1]
_BACKEND_SRC = _REPO_ROOT / "apps" / "backend" / "src"
_BACKEND_TESTS = _REPO_ROOT / "apps" / "backend" / "tests"
for _candidate in (_BACKEND_SRC, _BACKEND_TESTS):
    sp = str(_candidate)
    if _candidate.exists() and sp not in sys.path:
        sys.path.insert(0, sp)

from behavioral_equivalence.parity_lib import (  # type: ignore[import-not-found]  # noqa: E402  — path bootstrap above
    CharacterizationReport,
    default_thresholds,
    run_characterization,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_characterization",
        description="OmniTrade Phase 4.5 behavioural-equivalence characterization gate.",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Directory containing market_snapshots/ and baseline_decisions/.",
    )
    parser.add_argument(
        "--cassettes",
        type=Path,
        required=True,
        help="Directory containing vcrpy cassettes (one per snapshot id).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Minimum overall pass-rate (default 0.95).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Path to write the JSON characterization report.",
    )
    parser.add_argument(
        "--bucket-threshold",
        type=float,
        default=0.95,
        help="Minimum per-bucket pass-rate (default 0.95).",
    )
    parser.add_argument(
        "--drift-threshold",
        type=float,
        default=0.05,
        help="Maximum population-drift per action class (default 0.05).",
    )
    parser.add_argument(
        "--direction-threshold",
        type=float,
        default=0.95,
        help="Minimum direction consistency (default 0.95).",
    )
    return parser.parse_args(argv)


def _write_report(report: CharacterizationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _print_summary(report: CharacterizationReport) -> None:
    print(
        f"characterization: {report.passed}/{report.fixtures_total} "
        f"pass_rate={report.overall_pass_rate:.3f} "
        f"direction={report.direction_consistency:.3f}"
    )
    for bucket, stats in report.per_bucket.items():
        total = stats["total"]
        passed = stats["passed"]
        rate = stats["pass_rate"]
        print(f"  bucket[{bucket:<14}] {passed}/{total} rate={rate:.3f}")
    for action, drift in report.population_drift.items():
        print(f"  drift[{action:<13}] {drift:.3f}")
    if report.passed != report.fixtures_total:
        print("  failed fixtures:")
        for r in report.per_fixture:
            if not r.passed:
                reasons = "; ".join(r.failures) or "(no reasons)"
                print(f"    - {r.fixture_id}: {reasons}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:  # argparse already printed usage
        return int(exc.code) if isinstance(exc.code, int) else 2

    if not args.fixtures.exists():
        print(f"error: fixtures dir does not exist: {args.fixtures}", file=sys.stderr)
        return 2
    if not args.cassettes.exists():
        print(f"error: cassettes dir does not exist: {args.cassettes}", file=sys.stderr)
        return 2

    thresholds = default_thresholds(overall=args.threshold)
    thresholds["bucket"] = args.bucket_threshold
    thresholds["drift"] = args.drift_threshold
    thresholds["direction"] = args.direction_threshold

    try:
        report = run_characterization(
            fixtures_dir=args.fixtures,
            cassettes_dir=args.cassettes,
            thresholds=thresholds,
            run_at=datetime.now(tz=UTC).isoformat(),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _write_report(report, args.report)
    _print_summary(report)
    passed, reasons = report.all_gates_green()
    if not passed:
        print("GATE FAILED:", file=sys.stderr)
        for reason in reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 1
    print(f"GATE GREEN: report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
