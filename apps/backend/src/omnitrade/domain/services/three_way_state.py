"""Three-way state helper — isolates the atomic Position state contract.

The three fields (cumulative_close_pct, stop_loss, trailing_peak_pnl_pct)
on a Position MUST be updated together in one atomic SQL UPDATE.
This module is the single place that encodes that rule, so Phase 3
infrastructure can enforce the atomic UPDATE by consuming this function's output.

Splitting into three UPDATEs would create a race window with the 10-second
stop-loss monitor reading a stale ``stop_loss`` — hence the atomic contract.
"""

from __future__ import annotations

from decimal import Decimal

from omnitrade.domain.entities import Position


def apply_three_way_state(
    position: Position,
    new_cumulative_close_pct: Decimal,
    new_stop_loss: Decimal | None,
    new_trailing_peak: Decimal,
) -> Position:
    """Return a new Position with all three state-contract fields updated atomically.

    Phase 3 infrastructure MUST persist the output of this function in a single
    SQL UPDATE covering (cumulative_close_pct, stop_loss, trailing_peak_pnl_pct).
    Splitting into three UPDATEs would create a race window with the 10-second
    stop-loss monitor reading a stale stop_loss.

    Args:
        position: The current (immutable) Position.
        new_cumulative_close_pct: New cumulative percentage closed (0..100).
        new_stop_loss: New stop-loss override percentage (None to clear).
        new_trailing_peak: New peak PnL percentage (monotonically non-decreasing).

    Returns:
        A new Position instance with the three fields updated.
    """
    return position.apply_partial_close(
        new_pct=new_cumulative_close_pct,
        new_sl=new_stop_loss,
        new_peak=new_trailing_peak,
    )


def get_profit_protection_stop_percent(
    stage_trigger: Decimal,
    stage_index: int,
) -> Decimal:
    """Calculate the tightened stop-loss after a partial-profit stage triggers.

    After each partial-profit stage, stop-loss is set to a positive value
    (profit protection) so a reversal cannot erase the gains.

    Stage index 0 (first stage):  protect at trigger/2 (50% of stage gain)
    Stage index 1 (second stage): protect at trigger * 0.6 (60% of stage gain)
    Stage index 2 (third stage):  protect at trigger * 0.7 (70% of stage gain)

    Args:
        stage_trigger: The pnl% threshold that was crossed (positive Decimal).
        stage_index: 0-based index of the stage just triggered (0, 1, or 2).

    Returns:
        The new stop-loss % (positive number = profit-protection floor).
    """
    multipliers = [Decimal("0.5"), Decimal("0.6"), Decimal("0.7")]
    idx = min(stage_index, len(multipliers) - 1)
    return stage_trigger * multipliers[idx]
