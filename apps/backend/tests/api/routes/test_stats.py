"""GET /api/stats — Sharpe (log-returns of account_history), win-rate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from omnitrade.domain.entities import AccountSnapshot, Trade
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository


async def _seed(api_app, *, snapshots=(), trades=()) -> None:  # type: ignore[no-untyped-def]
    hist = AccountHistoryRepository()
    trepo = TradeRepository()
    open_session = api_app.state.test_session_factory
    session = await open_session()
    try:
        for s in snapshots:
            await hist.create(session, s)
        for t in trades:
            await trepo.create(session, t)
        await session.commit()
    finally:
        await session.close()


def _snap(offset_minutes: int, total: str) -> AccountSnapshot:
    return AccountSnapshot(
        timestamp=datetime(2026, 4, 18, tzinfo=UTC) + timedelta(minutes=offset_minutes),
        total_value=Decimal(total),
        available_cash=Decimal("500"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )


def _trade(order_id: str, pnl: str) -> Trade:
    return Trade(
        order_id=order_id,
        symbol="BTC_USDT",
        side="long",
        type="close",
        price=Decimal("100"),
        quantity=Decimal("1"),
        leverage=5,
        pnl=Decimal(pnl),
        fee=Decimal("0.1"),
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        status="filled",
    )


@pytest.mark.asyncio
async def test_stats_empty(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "total_return_percent": 0.0,
        "win_rate": 0.0,
        "n_trades": 0,
    }


@pytest.mark.asyncio
async def test_stats_win_rate_from_trades(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed(
        api_app,
        trades=[
            _trade("o-win-1", pnl="10"),
            _trade("o-win-2", pnl="5"),
            _trade("o-loss-1", pnl="-3"),
            _trade("o-loss-2", pnl="-7"),
        ],
    )
    resp = await api_client.get("/api/stats")
    body = resp.json()
    assert body["n_trades"] == 4
    assert body["win_rate"] == 0.5


@pytest.mark.asyncio
async def test_stats_sharpe_from_account_history_log_returns(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    # Strictly monotonically increasing → positive Sharpe.
    await _seed(
        api_app,
        snapshots=[
            _snap(0, "1000"),
            _snap(1, "1010"),
            _snap(2, "1025"),
            _snap(3, "1040"),
            _snap(4, "1060"),
        ],
    )
    resp = await api_client.get("/api/stats")
    body = resp.json()
    assert body["sharpe"] > 0
    assert body["total_return_percent"] == pytest.approx(6.0, abs=0.1)
    # Max drawdown on monotonic series is 0.
    assert body["max_drawdown"] == 0.0


@pytest.mark.asyncio
async def test_stats_max_drawdown_negative_on_peak_to_trough(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    await _seed(
        api_app,
        snapshots=[
            _snap(0, "1000"),
            _snap(1, "1200"),  # peak
            _snap(2, "900"),  # trough
            _snap(3, "1000"),
        ],
    )
    resp = await api_client.get("/api/stats")
    body = resp.json()
    # (900 - 1200) / 1200 = -0.25
    assert body["max_drawdown"] == pytest.approx(-0.25, abs=1e-6)
