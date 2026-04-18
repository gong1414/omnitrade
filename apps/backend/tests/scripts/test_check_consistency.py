"""check_consistency.py — read-only report + exit-code tests (Phase 8.6)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from omnitrade.infrastructure.persistence.models import Base

_REPO = Path(__file__).resolve().parents[2]
_CHK_PATH = _REPO / "scripts" / "check_consistency.py"
_spec = importlib.util.spec_from_file_location("check_consistency", _CHK_PATH)
assert _spec is not None and _spec.loader is not None
check_consistency = importlib.util.module_from_spec(_spec)
sys.modules["check_consistency"] = check_consistency
_spec.loader.exec_module(check_consistency)


async def _build_db(tmp_path: Path) -> str:
    db_path = tmp_path / "omnitrade_test.db"
    url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(async_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return url


@pytest.mark.asyncio
async def test_healthy_db_exits_zero(tmp_path: Path) -> None:
    url = await _build_db(tmp_path)
    async_url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    engine = create_async_engine(async_url)
    # Seed good rows.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO positions (symbol, quantity, entry_price, current_price, "
                "liquidation_price, unrealized_pnl, leverage, side, entry_order_id, "
                "opened_at, trailing_peak_pnl_pct, cumulative_close_pct) VALUES "
                "('BTC_USDT', 1.0, 100.0, 100.0, 0.0, 0.0, 5, 'long', 'ord-1', "
                "'2026-04-18 00:00:00+00:00', 0, 0)"
            )
        )
        now = datetime.now(tz=UTC)
        for i in range(3):
            ts = (now + timedelta(minutes=i)).isoformat()
            await conn.execute(
                text(
                    "INSERT INTO account_history (timestamp, total_value, available_cash,"
                    " unrealized_pnl, realized_pnl, return_percent) "
                    f"VALUES ('{ts}', 1000.0, 900.0, 0.0, 0.0, 0.0)"
                )
            )
    await engine.dispose()

    report = await check_consistency.run(url)
    assert report.schema_ok is True
    assert report.row_invariants_ok is True
    assert report.exit_code == 0


@pytest.mark.asyncio
async def test_bad_entry_price_fails(tmp_path: Path) -> None:
    url = await _build_db(tmp_path)
    async_url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    engine = create_async_engine(async_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO positions (symbol, quantity, entry_price, current_price, "
                "liquidation_price, unrealized_pnl, leverage, side, entry_order_id, "
                "opened_at, trailing_peak_pnl_pct, cumulative_close_pct) VALUES "
                "('ETH_USDT', 1.0, -100.0, 100.0, 0.0, 0.0, 5, 'long', 'ord-2', "
                "'2026-04-18 00:00:00+00:00', 0, 0)"
            )
        )
    await engine.dispose()

    report = await check_consistency.run(url)
    assert report.schema_ok is True
    assert report.row_invariants_ok is False
    assert report.exit_code == 1
    assert any(bp["symbol"] == "ETH_USDT" for bp in report.bad_positions)


@pytest.mark.asyncio
async def test_timestamp_regression_fails(tmp_path: Path) -> None:
    url = await _build_db(tmp_path)
    async_url = url.replace("sqlite:///", "sqlite+aiosqlite:///")
    engine = create_async_engine(async_url)
    async with engine.begin() as conn:
        # Insert two rows where id=2 has a timestamp BEFORE id=1.
        now = datetime.now(tz=UTC)
        earlier = (now - timedelta(hours=1)).isoformat()
        later = now.isoformat()
        await conn.execute(
            text(
                "INSERT INTO account_history (timestamp, total_value, available_cash, "
                "unrealized_pnl, realized_pnl, return_percent) "
                f"VALUES ('{later}', 1000.0, 900.0, 0.0, 0.0, 0.0)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO account_history (timestamp, total_value, available_cash, "
                "unrealized_pnl, realized_pnl, return_percent) "
                f"VALUES ('{earlier}', 1000.0, 900.0, 0.0, 0.0, 0.0)"
            )
        )
    await engine.dispose()

    report = await check_consistency.run(url)
    assert report.row_invariants_ok is False
    assert report.exit_code == 1
    assert len(report.timestamp_regressions) == 1
