"""Rebate formula test — 24h trace to 1e-9.

Exercises the 24-hour rebate formula on a hand-curated 4-trade sample:

    total_fees_usdt    = SUM(fee)  = 0.6812 + 0.3480 + 0.8905 + 1.3708
    rebate_amount_usdt = total_fees * 20 / 100

The assertion tolerance is 1e-9, giving the formula a tight contract
test without requiring a full 24h fixture JSON.
"""

from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal

import pytest

from omnitrade.application.rebate.service import RebateService
from omnitrade.domain.entities import Trade
from omnitrade.domain.services.rebate_calculator import calculate_rebate
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from tests.application._fakes import build_sqlite_session_factory

# Hand-curated 4-row sample with +08:00 (CST) timestamps; ``_CST`` retains
# the tz-offset and lets ``RebateService`` normalise to UTC internally.
_CST = timezone(timedelta(hours=8))

SAMPLE_TRADES = [
    {
        "id": 2001,
        "symbol": "BTC",
        "type": "close",
        "quantity": Decimal("1"),
        "price": Decimal("68120.4"),
        "fee": Decimal("0.6812"),
        "timestamp": datetime(2026, 4, 16, 12, 3, 11, tzinfo=_CST),
    },
    {
        "id": 2002,
        "symbol": "ETH",
        "type": "close",
        "quantity": Decimal("10"),
        "price": Decimal("3480.2"),
        "fee": Decimal("0.3480"),
        "timestamp": datetime(2026, 4, 16, 14, 41, 22, tzinfo=_CST),
    },
    {
        "id": 2003,
        "symbol": "SOL",
        "type": "close",
        "quantity": Decimal("100"),
        "price": Decimal("178.11"),
        "fee": Decimal("0.8905"),
        "timestamp": datetime(2026, 4, 16, 19, 15, 2, tzinfo=_CST),
    },
    {
        "id": 2004,
        "symbol": "BTC",
        "type": "close",
        "quantity": Decimal("2"),
        "price": Decimal("68540.0"),
        "fee": Decimal("1.3708"),
        "timestamp": datetime(2026, 4, 17, 2, 22, 7, tzinfo=_CST),
    },
]

# The formula applied to the 4-row sample.
EXPECTED_TOTAL_FEES = Decimal("0.6812") + Decimal("0.3480") + Decimal("0.8905") + Decimal("1.3708")
EXPECTED_REBATE = EXPECTED_TOTAL_FEES * Decimal("20") / Decimal("100")
TOLERANCE = Decimal("1e-9")


def _trades_from_samples() -> list[Trade]:
    return [
        Trade(
            order_id=f"close-{row['id']}",
            symbol=str(row["symbol"]),
            side="long",
            type=str(row["type"]),
            price=Decimal(str(row["price"])),
            quantity=Decimal(str(row["quantity"])),
            leverage=5,
            fee=Decimal(str(row["fee"])),
            timestamp=row["timestamp"],  # type: ignore[arg-type]
            status="filled",
        )
        for row in SAMPLE_TRADES
    ]


def test_formula_to_1e_minus_9() -> None:
    """Direct formula check on the calculator — no I/O."""
    # Anchor reference_time so all 4 rows fall inside the 24h window.
    # Anchor just after the last trade so all 4 rows fall inside the window.
    reference = datetime(2026, 4, 17, 6, tzinfo=_CST)
    total, rebate = calculate_rebate(
        _trades_from_samples(),
        fee_rebate_percent=Decimal("20"),
        window_hours=24,
        reference_time=reference,
    )
    assert abs(total - EXPECTED_TOTAL_FEES) < TOLERANCE
    assert abs(rebate - EXPECTED_REBATE) < TOLERANCE


@pytest.mark.asyncio
async def test_service_reproduces_formula_sample() -> None:
    """Service round-trip via in-memory SQLite reproduces the same numbers."""
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        repo = TradeRepository()
        for t in _trades_from_samples():
            await repo.create(session, t)
        await session.commit()
    finally:
        await session.close()

    svc = RebateService(
        trade_repo=TradeRepository(),
        session_factory=open_session,
        fee_rebate_percent=Decimal("20"),
        window_hours=24,
    )
    summary = await svc.compute_summary(
        reference_time=datetime(2026, 4, 17, 6, tzinfo=_CST),
    )
    assert summary.close_trades_count == 4
    assert abs(summary.total_fees_usdt - EXPECTED_TOTAL_FEES) < TOLERANCE
    assert abs(summary.rebate_amount_usdt - EXPECTED_REBATE) < TOLERANCE


@pytest.mark.asyncio
async def test_service_excludes_stale_trades() -> None:
    """A trade older than 24h is excluded."""
    _factory, open_session = await build_sqlite_session_factory()
    session = await open_session()
    try:
        repo = TradeRepository()
        for t in _trades_from_samples():
            await repo.create(session, t)
        # Old trade (48h before anchor) — must NOT contribute.
        await repo.create(
            session,
            Trade(
                order_id="stale",
                symbol="BTC",
                side="long",
                type="close",
                price=Decimal("1"),
                quantity=Decimal("1"),
                leverage=5,
                fee=Decimal("99.0"),
                timestamp=datetime(2026, 4, 15, tzinfo=UTC),
                status="filled",
            ),
        )
        await session.commit()
    finally:
        await session.close()

    svc = RebateService(
        trade_repo=TradeRepository(),
        session_factory=open_session,
        fee_rebate_percent=Decimal("20"),
        window_hours=24,
    )
    summary = await svc.compute_summary(
        reference_time=datetime(2026, 4, 17, 6, tzinfo=_CST),
    )
    # Stale fee 99 must NOT appear.
    assert abs(summary.total_fees_usdt - EXPECTED_TOTAL_FEES) < TOLERANCE
    assert summary.close_trades_count == 4
