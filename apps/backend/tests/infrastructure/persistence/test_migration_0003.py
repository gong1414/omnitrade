"""Round-trip test for Alembic 0003 — structured reasoning fields on agent_decisions.

Phase-9 Prompt Audit Modernization (PR-B1) — guards the addition of 6 nullable
columns to agent_decisions:

  market_context, gates_passed, invalidation_condition, plan, confidence, output_language

Drives alembic through:
  1. upgrade to 0002 (baseline)
  2. insert a legacy row (no new columns)
  3. upgrade to 0003 → assert 6 new columns present + legacy row has NULLs
  4. insert a row with new fields populated
  5. downgrade to 0002 → assert 6 columns gone + original legacy row still present

Note: SQLite .dump verification is documented here for completeness but not
executed automatically. To inspect manually:
  sqlite3 <db_path> ".dump agent_decisions"
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]

_NEW_COLUMNS = {
    "market_context",
    "gates_passed",
    "invalidation_condition",
    "plan",
    "confidence",
    "output_language",
}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def _decision_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(agent_decisions)").fetchall()
    finally:
        conn.close()
    return {row[1] for row in rows}


def _insert_legacy_row(db_path: Path) -> int:
    """Insert a legacy agent_decisions row (no new columns). Returns the rowid."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """INSERT INTO agent_decisions
               (timestamp, iteration, market_analysis, decision, actions_taken,
                account_value, positions_count)
               VALUES
               (datetime('now'), 1, 'legacy analysis', 'hold', 'none', 1000.0, 0)"""
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _fetch_decision_row(db_path: Path, rowid: int) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM agent_decisions WHERE id = ?", (rowid,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _decision_row_ids(db_path: Path) -> list[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id FROM agent_decisions").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def test_migration_0003_round_trip(tmp_path: Path) -> None:
    """Full upgrade/downgrade round-trip with data integrity checks."""
    db_path = tmp_path / "migration_0003_roundtrip.db"

    # Step 1: upgrade to 0002 baseline
    _alembic(db_path, "upgrade", "0002")
    cols = _decision_columns(db_path)
    assert not (_NEW_COLUMNS & cols), (
        f"Before 0003 upgrade: new columns must not exist yet, found: {_NEW_COLUMNS & cols}"
    )

    # Step 2: insert a legacy row (uses only pre-existing columns)
    legacy_id = _insert_legacy_row(db_path)
    assert legacy_id is not None

    # Step 3: upgrade to 0003 — 6 new columns must appear
    _alembic(db_path, "upgrade", "0003")
    cols = _decision_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols), (
        f"After upgrade 0003: expected {_NEW_COLUMNS} ⊆ columns, got {cols}"
    )

    # Step 3a: verify legacy row has NULL for all 6 new columns
    legacy_row = _fetch_decision_row(db_path, legacy_id)
    assert legacy_row, f"Legacy row id={legacy_id} missing after upgrade"
    for col in _NEW_COLUMNS:
        assert legacy_row[col] is None, (
            f"Legacy row column '{col}' should be NULL after upgrade, got {legacy_row[col]!r}"
        )

    # Step 4: insert a row with new fields populated
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """INSERT INTO agent_decisions
               (timestamp, iteration, market_analysis, decision, actions_taken,
                account_value, positions_count,
                market_context, gates_passed, invalidation_condition, plan,
                confidence, output_language)
               VALUES
               (datetime('now'), 2, 'structured analysis', 'buy', 'placed order', 1050.0, 1,
                ?, ?, ?, ?, ?, ?)""",
            (
                "x" * 200,
                json.dumps(["gate1", "gate2"]),
                "price drops below 95",
                json.dumps({"entry": 100.0, "target": 110.0}),
                0.75,
                "zh",
            ),
        )
        conn.commit()
        new_row_id = cur.lastrowid
    finally:
        conn.close()

    # verify the new row reads back correctly
    new_row = _fetch_decision_row(db_path, new_row_id)
    assert new_row["market_context"] == "x" * 200
    assert json.loads(new_row["gates_passed"]) == ["gate1", "gate2"]
    assert json.loads(new_row["plan"]) == {"entry": 100.0, "target": 110.0}
    assert abs(new_row["confidence"] - 0.75) < 1e-9
    assert new_row["output_language"] == "zh"

    # Step 5: downgrade to 0002 — 6 columns must disappear
    _alembic(db_path, "downgrade", "-1")
    cols = _decision_columns(db_path)
    assert not (_NEW_COLUMNS & cols), (
        f"After downgrade -1: new columns must be gone, still present: {_NEW_COLUMNS & cols}"
    )

    # Step 5a: legacy row must still exist after downgrade
    remaining_ids = _decision_row_ids(db_path)
    assert legacy_id in remaining_ids, (
        f"Legacy row id={legacy_id} missing after downgrade; remaining ids: {remaining_ids}"
    )

    legacy_row_post = _fetch_decision_row(db_path, legacy_id)
    assert legacy_row_post["market_analysis"] == "legacy analysis"
    assert legacy_row_post["decision"] == "hold"


def test_migration_0003_upgrade_head_round_trip(tmp_path: Path) -> None:
    """Verify upgrade head reaches 0003+ and columns are present."""
    db_path = tmp_path / "head_roundtrip.db"

    _alembic(db_path, "upgrade", "head")
    cols = _decision_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols), (
        f"After upgrade head: expected {_NEW_COLUMNS} ⊆ columns, got {cols}"
    )

    # downgrade -1 now goes to 0003 (not 0002), so 0003 columns remain
    _alembic(db_path, "downgrade", "-1")
    cols = _decision_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols), (
        f"After downgrade -1 (to 0003): expected {_NEW_COLUMNS} ⊆ columns, got {cols}"
    )

    # downgrade to 0002 should remove all 0003 columns
    _alembic(db_path, "downgrade", "0002")
    cols = _decision_columns(db_path)
    assert not (_NEW_COLUMNS & cols)

    _alembic(db_path, "upgrade", "head")
    cols = _decision_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols)


@pytest.mark.parametrize("col", sorted(_NEW_COLUMNS))
def test_new_column_individually_present(col: str, tmp_path: Path) -> None:
    db_path = tmp_path / f"col_{col}.db"
    _alembic(db_path, "upgrade", "0003")
    assert col in _decision_columns(db_path), (
        f"Column '{col}' not found in agent_decisions after upgrade 0003"
    )
