"""Risk service — three-tier drawdown policy with hypothesis invariant."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from omnitrade.application.risk_service import (
    DrawdownThresholds,
    RiskDecision,
    RiskService,
    classify_drawdown,
    compute_drawdown_percent,
)


@pytest.fixture
def thresholds() -> DrawdownThresholds:
    return DrawdownThresholds(
        warn_percent=Decimal("20"),
        block_open_percent=Decimal("30"),
        force_close_percent=Decimal("50"),
    )


def test_invariant_rejected_when_out_of_order() -> None:
    with pytest.raises(ValueError, match="warn < block_open < force_close"):
        DrawdownThresholds(
            warn_percent=Decimal("30"),
            block_open_percent=Decimal("20"),
            force_close_percent=Decimal("50"),
        )


def test_invariant_rejected_when_equal() -> None:
    with pytest.raises(ValueError, match="warn < block_open < force_close"):
        DrawdownThresholds(
            warn_percent=Decimal("20"),
            block_open_percent=Decimal("20"),
            force_close_percent=Decimal("50"),
        )


def test_compute_drawdown_zero_peak() -> None:
    assert compute_drawdown_percent(Decimal(0), Decimal(500)) == Decimal(0)


def test_compute_drawdown_current_above_peak() -> None:
    # no drawdown if current exceeds peak (rising curve)
    assert compute_drawdown_percent(Decimal(100), Decimal(150)) == Decimal(0)


def test_compute_drawdown_percentage() -> None:
    # 1000 peak → 800 current → 20% drawdown
    dd = compute_drawdown_percent(Decimal(1000), Decimal(800))
    assert dd == Decimal(20)


def test_classify_ok(thresholds: DrawdownThresholds) -> None:
    assert classify_drawdown(Decimal(10), thresholds) == RiskDecision.OK


def test_classify_warn(thresholds: DrawdownThresholds) -> None:
    assert classify_drawdown(Decimal("20"), thresholds) == RiskDecision.WARN
    assert classify_drawdown(Decimal("25"), thresholds) == RiskDecision.WARN


def test_classify_block_open(thresholds: DrawdownThresholds) -> None:
    assert classify_drawdown(Decimal("30"), thresholds) == RiskDecision.BLOCK_OPEN
    assert classify_drawdown(Decimal("40"), thresholds) == RiskDecision.BLOCK_OPEN


def test_classify_force_close(thresholds: DrawdownThresholds) -> None:
    assert classify_drawdown(Decimal("50"), thresholds) == RiskDecision.FORCE_CLOSE
    assert classify_drawdown(Decimal("99"), thresholds) == RiskDecision.FORCE_CLOSE


def test_service_apply_end_to_end(thresholds: DrawdownThresholds) -> None:
    svc = RiskService(thresholds)
    # 1000 → 700 = 30% drawdown → BLOCK_OPEN
    assert svc.apply(Decimal(1000), Decimal(700)) == RiskDecision.BLOCK_OPEN


def test_service_thresholds_accessor(thresholds: DrawdownThresholds) -> None:
    svc = RiskService(thresholds)
    assert svc.thresholds is thresholds


# ── hypothesis invariant: warn < block < force_close always holds ────── #


_threshold_strategy = st.builds(
    DrawdownThresholds,
    warn_percent=st.decimals(min_value=Decimal("1"), max_value=Decimal("29"), places=2),
    block_open_percent=st.decimals(min_value=Decimal("30"), max_value=Decimal("49"), places=2),
    force_close_percent=st.decimals(min_value=Decimal("50"), max_value=Decimal("95"), places=2),
)


@given(_threshold_strategy)
def test_invariant_always_holds(t: DrawdownThresholds) -> None:
    """Any successfully-constructed DrawdownThresholds satisfies warn < block < force_close."""
    assert t.warn_percent < t.block_open_percent < t.force_close_percent


@given(_threshold_strategy, st.decimals(min_value=Decimal(0), max_value=Decimal(100), places=2))
def test_classify_is_monotonic(t: DrawdownThresholds, dd: Decimal) -> None:
    """Higher drawdown never yields a weaker decision."""
    step = Decimal("0.5")
    base = classify_drawdown(dd, t)
    higher = classify_drawdown(dd + step, t)
    ordering = [
        RiskDecision.OK,
        RiskDecision.WARN,
        RiskDecision.BLOCK_OPEN,
        RiskDecision.FORCE_CLOSE,
    ]
    assert ordering.index(higher) >= ordering.index(base)
