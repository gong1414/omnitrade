"""Tests for rebate calculator — 24h window and default 20% rate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from omnitrade.domain.entities import Trade
from omnitrade.domain.services.rebate_calculator import calculate_rebate


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _make_trade(
    trade_type: str,
    fee: Decimal | None,
    timestamp: datetime,
    order_id: str = "ord-001",
) -> Trade:
    return Trade(
        order_id=order_id,
        symbol="BTCUSDT",
        side="long",
        type=trade_type,
        price=Decimal("68000"),
        quantity=Decimal("0.1"),
        leverage=10,
        timestamp=timestamp,
        fee=fee,
    )


class TestCalculateRebate:
    def test_basic_20_percent_default(self) -> None:
        now = _utcnow()
        trades = [
            _make_trade("close", Decimal("1.0"), now - timedelta(hours=1)),
            _make_trade("close", Decimal("2.0"), now - timedelta(hours=2)),
        ]
        total_fees, rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("3.0")
        # 20% of 3.0 = 0.6
        assert rebate == Decimal("0.6")

    def test_only_close_trades_counted(self) -> None:
        now = _utcnow()
        trades = [
            _make_trade("close", Decimal("2.0"), now - timedelta(hours=1)),
            _make_trade("open", Decimal("1.0"), now - timedelta(hours=1), order_id="ord-002"),
        ]
        total_fees, rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("2.0")
        assert rebate == Decimal("0.4")

    def test_outside_window_excluded(self) -> None:
        now = _utcnow()
        trades = [
            _make_trade("close", Decimal("5.0"), now - timedelta(hours=25)),  # outside 24h
            _make_trade("close", Decimal("3.0"), now - timedelta(hours=12)),  # inside
        ]
        total_fees, rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("3.0")
        assert rebate == Decimal("0.6")

    def test_none_fee_skipped(self) -> None:
        now = _utcnow()
        trades = [
            _make_trade("close", None, now - timedelta(hours=1)),
            _make_trade("close", Decimal("2.0"), now - timedelta(hours=2)),
        ]
        total_fees, _rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("2.0")

    def test_custom_rebate_percent(self) -> None:
        now = _utcnow()
        trades = [_make_trade("close", Decimal("10.0"), now - timedelta(hours=1))]
        _total_fees, rebate = calculate_rebate(
            trades, fee_rebate_percent=Decimal("30"), reference_time=now
        )
        assert rebate == Decimal("3.0")

    def test_zero_trades(self) -> None:
        total_fees, rebate = calculate_rebate([], reference_time=_utcnow())
        assert total_fees == Decimal("0")
        assert rebate == Decimal("0")

    def test_exact_boundary_at_24h(self) -> None:
        """Trade at exactly 24h ago should be included (>= cutoff)."""
        now = _utcnow()
        exactly_24h = now - timedelta(hours=24)
        trades = [_make_trade("close", Decimal("1.0"), exactly_24h)]
        total_fees, _rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("1.0")

    def test_sample_24h_rebate(self) -> None:
        """Exercise the 24h JSON sample via the calculator.

        The sample uses +08:00 timestamps; here we test with UTC equivalents.
        reference_time = 2026-04-17T10:00:00Z  (i.e., 18:00 +08:00)
        cutoff         = 2026-04-16T10:00:00Z

        UTC timestamps of the 4 sample trades:
          2001: 2026-04-16T04:03:11Z  → BEFORE cutoff, excluded
          2002: 2026-04-16T06:41:22Z  → BEFORE cutoff, excluded
          2003: 2026-04-16T11:15:02Z  → after cutoff, included
          2004: 2026-04-16T18:22:07Z  → after cutoff, included

        Included total = 0.8905 + 1.3708 = 2.2613
        rebate = 2.2613 * 20% = 0.45226
        """
        now = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
        trades = [
            _make_trade(
                "close",
                Decimal("0.6812"),
                datetime(2026, 4, 16, 4, 3, 11, tzinfo=UTC),
                "2001",
            ),
            _make_trade(
                "close",
                Decimal("0.3480"),
                datetime(2026, 4, 16, 6, 41, 22, tzinfo=UTC),
                "2002",
            ),
            _make_trade(
                "close",
                Decimal("0.8905"),
                datetime(2026, 4, 16, 11, 15, 2, tzinfo=UTC),
                "2003",
            ),
            _make_trade(
                "close",
                Decimal("1.3708"),
                datetime(2026, 4, 16, 18, 22, 7, tzinfo=UTC),
                "2004",
            ),
        ]
        total_fees, rebate = calculate_rebate(
            trades, fee_rebate_percent=Decimal("20"), reference_time=now
        )
        # Only trades 2003 and 2004 fall within the 24h window
        assert total_fees == Decimal("2.2613")
        assert rebate == Decimal("0.45226")

    def test_naive_timestamp_treated_as_utc(self) -> None:
        """Trades with naive timestamps should be treated as UTC."""
        now = datetime.now(tz=UTC)
        naive_ts = now - timedelta(hours=2)
        naive_ts = naive_ts.replace(tzinfo=None)  # strip tz
        trades = [_make_trade("close", Decimal("1.0"), naive_ts)]
        total_fees, _rebate = calculate_rebate(trades, reference_time=now)
        assert total_fees == Decimal("1.0")
