"""Regression lock for Alembic 0002 — column rename round-trip.

Guards the Phase-9.2 rename:
  peak_pnl_percent         → trailing_peak_pnl_pct
  partial_close_percentage → cumulative_close_pct

The test drives alembic through ``upgrade head`` on a disposable SQLite
DB, introspects ``positions``, then ``downgrade -1`` to confirm the old
names come back. Any future migration that clobbers this rename will
fail this test loudly.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]

_NEW_COLUMNS = {"trailing_peak_pnl_pct", "cumulative_close_pct"}
_OLD_COLUMNS = {"peak_pnl_percent", "partial_close_percentage"}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def _position_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(positions)").fetchall()
    finally:
        conn.close()
    return {row[1] for row in rows}


def test_alembic_0002_upgrade_downgrade_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "rename_roundtrip.db"

    _alembic(db_path, "upgrade", "head")
    cols = _position_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols), (
        f"after upgrade head: expected {_NEW_COLUMNS} ⊆ columns, got {cols}"
    )
    assert not (_OLD_COLUMNS & cols), (
        f"after upgrade head: legacy columns must be gone, still present: {_OLD_COLUMNS & cols}"
    )

    _alembic(db_path, "downgrade", "0001")
    cols = _position_columns(db_path)
    assert _OLD_COLUMNS.issubset(cols), (
        f"after downgrade to 0001: expected {_OLD_COLUMNS} ⊆ columns, got {cols}"
    )
    assert not (_NEW_COLUMNS & cols), (
        f"after downgrade to 0001: renamed columns must be absent, still present: {_NEW_COLUMNS & cols}"
    )

    _alembic(db_path, "upgrade", "head")
    cols = _position_columns(db_path)
    assert _NEW_COLUMNS.issubset(cols)
    assert not (_OLD_COLUMNS & cols)


@pytest.mark.parametrize("col", sorted(_NEW_COLUMNS))
def test_new_columns_individually_present(col: str, tmp_path: Path) -> None:
    db_path = tmp_path / f"roundtrip_{col}.db"
    _alembic(db_path, "upgrade", "head")
    assert col in _position_columns(db_path)
