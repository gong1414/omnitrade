"""sync_positions.py — CLI safety-gate + diff/apply tests (Phase 8.6)."""

from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from omnitrade.domain.entities import Position
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from tests.application._fakes import build_sqlite_session_factory, make_position

# ``scripts/`` is a sibling of ``src/`` — load the module by path so we
# don't need to pollute PYTHONPATH or ship a setup.py entry for the CLI.
_REPO = Path(__file__).resolve().parents[2]
_SYNC_PATH = _REPO / "scripts" / "sync_positions.py"
_spec = importlib.util.spec_from_file_location("sync_positions", _SYNC_PATH)
assert _spec is not None and _spec.loader is not None
sync_positions = importlib.util.module_from_spec(_spec)
sys.modules["sync_positions"] = sync_positions
_spec.loader.exec_module(sync_positions)


class _StubExchange:
    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions

    async def fetch_positions(self) -> list[Position]:
        return list(self._positions)


def _pos(sym: str, qty: Decimal, pid: int | None = None) -> Position:
    """Make a Position; ``pid=None`` → let SQLite auto-assign on insert."""
    pos = make_position(pid=pid if pid is not None else 1, symbol=sym, quantity=qty)
    if pid is None:
        pos = pos.model_copy(update={"id": None})
    return pos


# ── compute_diff ──────────────────────────────────────────────────── #


def test_compute_diff_only_on_exchange() -> None:
    ex = [_pos("BTC_USDT", Decimal("1"))]
    lo: list[Position] = []
    diff = sync_positions.compute_diff(ex, lo)
    assert [p.symbol for p in diff.only_on_exchange] == ["BTC_USDT"]
    assert diff.only_in_local == []
    assert diff.size_mismatch == []


def test_compute_diff_only_in_local() -> None:
    ex: list[Position] = []
    lo = [_pos("ETH_USDT", Decimal("2"), pid=5)]
    diff = sync_positions.compute_diff(ex, lo)
    assert [p.symbol for p in diff.only_in_local] == ["ETH_USDT"]
    assert diff.only_on_exchange == []
    assert diff.size_mismatch == []


def test_compute_diff_size_mismatch() -> None:
    ex = [_pos("BTC_USDT", Decimal("3"))]
    lo = [_pos("BTC_USDT", Decimal("1"), pid=1)]
    diff = sync_positions.compute_diff(ex, lo)
    assert diff.only_on_exchange == []
    assert diff.only_in_local == []
    assert len(diff.size_mismatch) == 1
    ex_p, lo_p = diff.size_mismatch[0]
    assert ex_p.quantity == Decimal("3")
    assert lo_p.quantity == Decimal("1")


# ── run() with in-memory DB ───────────────────────────────────────── #


@pytest.mark.asyncio
async def test_run_dry_run_leaves_db_unchanged() -> None:
    factory, _open_session = await build_sqlite_session_factory()
    repo = PositionRepository()

    # Pre-seed local with one position; exchange has a different one.
    async with factory() as s:
        await repo.create(s, _pos("ETH_USDT", Decimal("1")))
        await s.commit()

    exchange = _StubExchange([_pos("BTC_USDT", Decimal("2"))])
    rc = await sync_positions.run(
        exchange=exchange,  # type: ignore[arg-type]
        session_factory=factory,
        apply=False,
        non_interactive=True,
    )
    assert rc == 0

    async with factory() as s:
        rows = await repo.list_all(s)
    # Dry-run: local should still be the pre-seeded ETH_USDT only.
    assert [p.symbol for p in rows] == ["ETH_USDT"]


@pytest.mark.asyncio
async def test_run_apply_overwrites_local_to_match_exchange() -> None:
    factory, _open_session = await build_sqlite_session_factory()
    repo = PositionRepository()
    async with factory() as s:
        await repo.create(s, _pos("ETH_USDT", Decimal("1")))
        await s.commit()

    exchange = _StubExchange([_pos("BTC_USDT", Decimal("2"))])
    rc = await sync_positions.run(
        exchange=exchange,  # type: ignore[arg-type]
        session_factory=factory,
        apply=True,
        non_interactive=True,
    )
    assert rc == 0

    async with factory() as s:
        rows = await repo.list_all(s)
    symbols = sorted(p.symbol for p in rows)
    # ETH deleted (only_in_local) + BTC created (only_on_exchange).
    assert symbols == ["BTC_USDT"]


# ── main() safety gates (stdin fd check) ──────────────────────────── #


def test_main_apply_without_yes_really_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate non-TTY so the safety check fires even on interactive
    # runners.
    monkeypatch.setattr(sync_positions.sys.stdin, "isatty", lambda: False)
    rc = sync_positions.main(["--apply"])
    assert rc == 2


def test_main_non_tty_without_apply_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_positions.sys.stdin, "isatty", lambda: False)
    rc = sync_positions.main([])
    assert rc == 2


def test_main_non_interactive_requires_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_positions.sys.stdin, "isatty", lambda: True)
    rc = sync_positions.main(["--non-interactive"])
    assert rc == 2


def test_cli_entrypoint_file_is_executable() -> None:
    """Sanity — the script file exists and is valid Python (importable)."""
    assert _SYNC_PATH.exists()
    assert os.path.getsize(_SYNC_PATH) > 0
    assert hasattr(sync_positions, "main")
