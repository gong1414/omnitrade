"""check_consistency.py — read-only DB sanity report (Phase 8.6).

Inspects schema + row-level invariants of the production SQLite DB.
Emits a JSON report to stdout and exits non-zero if any assertion
fails. The script NEVER writes — there is no ``--apply`` flag. Safe to
run against prod.

Assertions
----------
- Every declared ORM table is present in the live DB.
- Each ORM table has at least one primary-key column.
- ``positions.entry_price`` > 0 and ``positions.quantity`` > 0 for all
  rows.
- ``account_history.timestamp`` is monotonically non-decreasing when
  ordered by ``id``.

Exit codes
----------
- ``0`` all assertions pass.
- ``1`` one or more assertions fail (report still printed).
- ``2`` unexpected exception.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any, cast

import structlog

if __package__ in (None, ""):
    import os

    _HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine

from omnitrade.config import get_settings
from omnitrade.infrastructure.persistence.database import build_engines
from omnitrade.infrastructure.persistence.models import (
    AccountHistoryORM,
    Base,
    PositionORM,
)

logger = structlog.get_logger(__name__)


@dataclass
class ConsistencyReport:
    """Aggregated consistency findings."""

    schema_ok: bool = True
    row_invariants_ok: bool = True
    missing_tables: list[str] = field(default_factory=list)
    tables_without_pk: list[str] = field(default_factory=list)
    bad_positions: list[dict[str, Any]] = field(default_factory=list)
    timestamp_regressions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 0 if self.schema_ok and self.row_invariants_ok else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_ok": self.schema_ok,
            "row_invariants_ok": self.row_invariants_ok,
            "missing_tables": self.missing_tables,
            "tables_without_pk": self.tables_without_pk,
            "bad_positions": self.bad_positions,
            "timestamp_regressions": self.timestamp_regressions,
        }


def _check_schema(sync_engine: Any) -> tuple[list[str], list[str]]:
    """Return (missing_tables, tables_without_pk)."""
    inspector = inspect(sync_engine)
    live_tables = set(inspector.get_table_names())
    declared_tables = set(Base.metadata.tables.keys())

    missing = sorted(declared_tables - live_tables)
    no_pk: list[str] = []
    for tbl_name in sorted(declared_tables & live_tables):
        pk = inspector.get_pk_constraint(tbl_name)
        cols = pk.get("constrained_columns") or []
        if not cols:
            no_pk.append(tbl_name)
    return missing, no_pk


async def _check_positions(async_engine: AsyncEngine) -> list[dict[str, Any]]:
    """Return bad-position records (entry_price ≤ 0 or quantity ≤ 0)."""
    bad: list[dict[str, Any]] = []
    async with async_engine.connect() as conn:
        result = await conn.execute(
            select(
                PositionORM.id,
                PositionORM.symbol,
                PositionORM.entry_price,
                PositionORM.quantity,
            )
        )
        for row in result:
            pid, symbol, entry_price, quantity = row
            if entry_price is None or entry_price <= 0 or quantity is None or quantity <= 0:
                bad.append(
                    {
                        "id": pid,
                        "symbol": symbol,
                        "entry_price": (
                            float(entry_price) if entry_price is not None else None
                        ),
                        "quantity": float(quantity) if quantity is not None else None,
                    }
                )
    return bad


async def _check_account_history(async_engine: AsyncEngine) -> list[dict[str, Any]]:
    """Return regression records where timestamp decreases with increasing id."""
    regressions: list[dict[str, Any]] = []
    async with async_engine.connect() as conn:
        result = await conn.execute(
            select(AccountHistoryORM.id, AccountHistoryORM.timestamp).order_by(
                AccountHistoryORM.id
            )
        )
        prev_ts: Any = None
        prev_id: int | None = None
        for row in result:
            row_id, ts = row
            if prev_ts is not None and ts is not None and ts < prev_ts:
                regressions.append(
                    {
                        "prev_id": prev_id,
                        "prev_timestamp": str(prev_ts),
                        "row_id": row_id,
                        "timestamp": str(ts),
                    }
                )
            prev_ts = ts
            prev_id = row_id
    return regressions


async def run(database_url: str) -> ConsistencyReport:
    """Build engines + run all checks. Returns a fresh ConsistencyReport."""
    sync_engine, _sync_factory, async_engine_obj, _async_factory = build_engines(database_url)
    async_engine = cast(AsyncEngine, async_engine_obj)
    report = ConsistencyReport()

    missing, no_pk = _check_schema(sync_engine)
    report.missing_tables = missing
    report.tables_without_pk = no_pk
    if missing or no_pk:
        report.schema_ok = False

    try:
        report.bad_positions = await _check_positions(async_engine)
        report.timestamp_regressions = await _check_account_history(async_engine)
    finally:
        await async_engine.dispose()

    if report.bad_positions or report.timestamp_regressions:
        report.row_invariants_ok = False

    logger.info(
        "check_consistency.summary",
        schema_ok=report.schema_ok,
        row_invariants_ok=report.row_invariants_ok,
        n_missing_tables=len(report.missing_tables),
        n_bad_positions=len(report.bad_positions),
        n_ts_regressions=len(report.timestamp_regressions),
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_consistency",
        description="Read-only DB consistency report (schema + row invariants).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL (otherwise uses Settings).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db_url = args.database_url or get_settings().database_url

    try:
        report = asyncio.run(run(db_url))
    except Exception as exc:
        logger.error("check_consistency.failed", error=str(exc), exc_info=True)
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        return 2

    print(json.dumps(report.to_dict(), indent=2, default=str))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ConsistencyReport", "build_parser", "main", "run"]
