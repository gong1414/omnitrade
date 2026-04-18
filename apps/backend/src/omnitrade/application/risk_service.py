"""Risk service — three-tier drawdown policy.

Per consensus plan §5 AC:
  - warn at `settings.account_drawdown_warning_percent` (default 20%)
  - block-open at `settings.account_drawdown_no_new_position_percent` (default 30%)
  - liquidate (force-close) at `settings.account_drawdown_force_close_percent` (default 50%)

Invariant: ``warn < block_open < force_close`` (all strictly ordered).
Returned ``RiskDecision`` tells the caller which bucket the current drawdown
falls into.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class RiskDecision(StrEnum):
    """Discrete risk bucket for the current drawdown level."""

    OK = "ok"
    WARN = "warn"
    BLOCK_OPEN = "block_open"
    FORCE_CLOSE = "force_close"


@dataclass(frozen=True)
class DrawdownThresholds:
    """Three strictly-ordered drawdown thresholds (all positive percentages)."""

    warn_percent: Decimal
    block_open_percent: Decimal
    force_close_percent: Decimal

    def __post_init__(self) -> None:
        if not (self.warn_percent < self.block_open_percent < self.force_close_percent):
            raise ValueError(
                "DrawdownThresholds must satisfy "
                "warn < block_open < force_close, got "
                f"{self.warn_percent} / {self.block_open_percent} / {self.force_close_percent}"
            )


def compute_drawdown_percent(peak: Decimal, current: Decimal) -> Decimal:
    """Compute drawdown as a non-negative percentage (0..100).

    Returns 0 when peak is 0 or current >= peak. Positive when current < peak.
    """
    if peak <= Decimal(0):
        return Decimal(0)
    diff = peak - current
    if diff <= Decimal(0):
        return Decimal(0)
    return (diff / peak) * Decimal(100)


def classify_drawdown(
    drawdown_percent: Decimal,
    thresholds: DrawdownThresholds,
) -> RiskDecision:
    """Map the drawdown percentage to the discrete ``RiskDecision`` bucket.

    Monotonic in ``drawdown_percent``: higher drawdown → same-or-worse decision.
    """
    if drawdown_percent >= thresholds.force_close_percent:
        return RiskDecision.FORCE_CLOSE
    if drawdown_percent >= thresholds.block_open_percent:
        return RiskDecision.BLOCK_OPEN
    if drawdown_percent >= thresholds.warn_percent:
        return RiskDecision.WARN
    return RiskDecision.OK


class RiskService:
    """Applies the three-tier drawdown policy.

    The service is stateless — all context arrives via method arguments.
    Thresholds are supplied at construction time so tests can parametrise.
    """

    def __init__(self, thresholds: DrawdownThresholds) -> None:
        self._thresholds = thresholds

    @property
    def thresholds(self) -> DrawdownThresholds:
        return self._thresholds

    def apply(self, peak: Decimal, current: Decimal) -> RiskDecision:
        """Return the ``RiskDecision`` for the given peak / current pair."""
        drawdown = compute_drawdown_percent(peak, current)
        decision = classify_drawdown(drawdown, self._thresholds)
        with_context(logger).info(
            "risk_service.apply",
            peak=str(peak),
            current=str(current),
            drawdown_percent=str(drawdown),
            decision=decision.value,
        )
        return decision


__all__ = [
    "DrawdownThresholds",
    "RiskDecision",
    "RiskService",
    "classify_drawdown",
    "compute_drawdown_percent",
]
