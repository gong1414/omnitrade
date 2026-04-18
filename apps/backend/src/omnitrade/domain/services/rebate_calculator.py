"""Rebate calculator — pure function, no I/O.

Formula:
  rebate_amount = SUM(fee for close trades in 24h window) * fee_rebate_percent / 100

Default fee_rebate_percent = 20 (meaning 20% of close-trade fees are rebated).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from omnitrade.domain.entities import Trade

_DEFAULT_FEE_REBATE_PERCENT: Decimal = Decimal("20")


def calculate_rebate(
    trades: list[Trade],
    fee_rebate_percent: Decimal = _DEFAULT_FEE_REBATE_PERCENT,
    window_hours: int = 24,
    reference_time: datetime | None = None,
) -> tuple[Decimal, Decimal]:
    """Calculate the 24-hour rebate total from a list of trades.

    Args:
        trades: All trade records to consider (may span more than 24h).
        fee_rebate_percent: Rebate percentage (0..100). Default 20.
        window_hours: Look-back window in hours. Default 24.
        reference_time: The "now" anchor for the window. Defaults to UTC now.

    Returns:
        Tuple of (total_fees_in_window, rebate_amount).
        rebate_amount = total_fees * fee_rebate_percent / 100
    """
    if reference_time is None:
        reference_time = datetime.now(tz=UTC)

    # Ensure reference_time is tz-aware
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)

    cutoff = reference_time - timedelta(hours=window_hours)

    total_fees = Decimal("0")
    for trade in trades:
        # Only close trades contribute rebate
        if trade.type != "close":
            continue
        if trade.fee is None:
            continue

        # Normalise trade timestamp to tz-aware for comparison
        ts = trade.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        if ts >= cutoff:
            total_fees += trade.fee

    rebate_amount = total_fees * fee_rebate_percent / Decimal("100")
    return total_fees, rebate_amount
