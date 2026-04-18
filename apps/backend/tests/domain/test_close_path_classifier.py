"""Tests for close-path classifier — parametrized across all 5 buckets + edge cases."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.domain.entities import Position
from omnitrade.domain.enums import ClosePath
from omnitrade.domain.services.close_path_classifier import (
    PartialProfitStage,
    StopLossParams,
    TrailingStopLevel,
    classify_close_path,
    get_stop_loss_threshold,
)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _base_position(**kwargs: object) -> Position:
    defaults: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("1"),
        "entry_price": Decimal("68000"),
        "current_price": Decimal("69000"),
        "liquidation_price": Decimal("50000"),
        "unrealized_pnl": Decimal("1000"),
        "leverage": 10,
        "side": "long",
        "entry_order_id": "order-001",
        "opened_at": _utcnow(),
        "trailing_peak_pnl_pct": Decimal("0"),
        "cumulative_close_pct": Decimal("0"),
        "stop_loss": None,
    }
    defaults.update(kwargs)
    return Position(**defaults)  # type: ignore[arg-type]


_SL_PARAMS = StopLossParams(
    low=Decimal("-8"),
    mid=Decimal("-6"),
    high=Decimal("-5"),
    mid_leverage_threshold=10,
    high_leverage_threshold=20,
)

_TRAILING_LEVELS = [
    TrailingStopLevel(trigger=Decimal("15"), stop_at=Decimal("8")),
    TrailingStopLevel(trigger=Decimal("10"), stop_at=Decimal("5")),
    TrailingStopLevel(trigger=Decimal("5"), stop_at=Decimal("2")),
]

_PARTIAL_STAGES = [
    PartialProfitStage(trigger=Decimal("8"), close_percent=Decimal("30")),
    PartialProfitStage(trigger=Decimal("12"), close_percent=Decimal("60")),
    PartialProfitStage(trigger=Decimal("18"), close_percent=Decimal("100")),
]


# ── get_stop_loss_threshold ────────────────────────────────────────────────────── #


class TestGetStopLossThreshold:
    def test_override_used_when_set(self) -> None:
        pos = _base_position(stop_loss=Decimal("3"), leverage=10)
        threshold = get_stop_loss_threshold(pos, _SL_PARAMS)
        assert threshold == Decimal("3")

    def test_low_band_selected(self) -> None:
        pos = _base_position(leverage=5)
        threshold = get_stop_loss_threshold(pos, _SL_PARAMS)
        assert threshold == Decimal("-8")

    def test_mid_band_selected(self) -> None:
        pos = _base_position(leverage=10)
        threshold = get_stop_loss_threshold(pos, _SL_PARAMS)
        assert threshold == Decimal("-6")

    def test_high_band_selected(self) -> None:
        pos = _base_position(leverage=20)
        threshold = get_stop_loss_threshold(pos, _SL_PARAMS)
        assert threshold == Decimal("-5")

    def test_positive_override_profit_protection(self) -> None:
        # After partial profit, stop_loss may be positive (profit floor)
        pos = _base_position(stop_loss=Decimal("4"), leverage=15)
        threshold = get_stop_loss_threshold(pos, _SL_PARAMS)
        assert threshold == Decimal("4")


# ── classify_close_path ───────────────────────────────────────────────────────── #


@pytest.mark.parametrize(
    "current_pnl,peak_pnl,partial_pct,stop_loss_override,enable_code,ai_decision,expected",
    [
        # stop_loss bucket — pnl below threshold
        (
            Decimal("-7"),
            Decimal("0"),
            Decimal("0"),
            None,
            False,
            None,
            ClosePath.STOP_LOSS,
        ),
        # stop_loss — exactly at threshold (boundary)
        (
            Decimal("-6"),
            Decimal("0"),
            Decimal("0"),
            None,
            False,
            None,
            ClosePath.STOP_LOSS,
        ),
        # trailing_stop bucket
        (
            Decimal("3"),  # dropped below level.stop_at=5
            Decimal("12"),  # peak >= level.trigger=10
            Decimal("0"),
            None,
            True,
            None,
            ClosePath.TRAILING_STOP,
        ),
        # partial_profit bucket — stage 1 triggered
        (
            Decimal("9"),  # >= stage1.trigger=8
            Decimal("0"),
            Decimal("0"),  # no partial close yet
            None,
            False,
            None,
            ClosePath.PARTIAL_PROFIT,
        ),
        # partial_profit bucket — stage 2 triggered
        (
            Decimal("13"),
            Decimal("0"),
            Decimal("30"),  # stage 1 already done
            None,
            False,
            None,
            ClosePath.PARTIAL_PROFIT,
        ),
        # ai_decision bucket
        (
            Decimal("2"),
            Decimal("0"),
            Decimal("0"),
            None,
            False,
            {"action": "close", "reason": "test"},
            ClosePath.AI_DECISION,
        ),
        # none bucket — no close signal
        (
            Decimal("3"),
            Decimal("0"),
            Decimal("0"),
            None,
            False,
            None,
            ClosePath.NONE,
        ),
        # none bucket — ai_decision with action != close
        (
            Decimal("3"),
            Decimal("0"),
            Decimal("0"),
            None,
            False,
            {"action": "hold"},
            ClosePath.NONE,
        ),
    ],
)
def test_classify_parametrized(
    current_pnl: Decimal,
    peak_pnl: Decimal,
    partial_pct: Decimal,
    stop_loss_override: Decimal | None,
    enable_code: bool,
    ai_decision: dict | None,
    expected: ClosePath,
) -> None:
    pos = _base_position(
        trailing_peak_pnl_pct=peak_pnl,
        cumulative_close_pct=partial_pct,
        stop_loss=stop_loss_override,
    )
    result = classify_close_path(
        position=pos,
        current_pnl_percent=current_pnl,
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=enable_code,
        ai_decision=ai_decision,
    )
    assert result == expected


def test_partial_profit_takes_priority_over_trailing_stop() -> None:
    """partial_profit is checked before trailing_stop.

    pnl=9 crosses stage1 (trigger=8), AND peak=12 >= level2 trigger=10 with pnl=4 <= stop_at=5.
    Since partial_profit is evaluated first in classify_close_path, it wins.
    """
    pos = _base_position(
        trailing_peak_pnl_pct=Decimal("12"),
        cumulative_close_pct=Decimal("0"),
        stop_loss=None,
    )
    # pnl=9 crosses stage1 (trigger=8) → partial_profit fires before trailing is checked
    result = classify_close_path(
        position=pos,
        current_pnl_percent=Decimal("9"),
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=True,
        ai_decision=None,
    )
    assert result == ClosePath.PARTIAL_PROFIT


def test_trailing_stop_disabled_when_not_enabled() -> None:
    """Trailing stop must not fire when enableCodeLevelProtection=False.

    With all partial stages done and trailing disabled and pnl above stop-loss threshold,
    no close path fires → NONE.
    """
    pos = _base_position(trailing_peak_pnl_pct=Decimal("20"), cumulative_close_pct=Decimal("100"))
    result = classify_close_path(
        position=pos,
        current_pnl_percent=Decimal("8"),  # above stop-loss threshold (-6 mid band)
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=False,
        ai_decision=None,
    )
    # All partial stages done, trailing disabled, pnl positive → NONE
    assert result == ClosePath.NONE


def test_trailing_stop_fires_when_disabled_false_but_pnl_below_sl() -> None:
    """With code-level protection disabled, stop_loss still fires on loss."""
    pos = _base_position(trailing_peak_pnl_pct=Decimal("20"), cumulative_close_pct=Decimal("100"))
    result = classify_close_path(
        position=pos,
        current_pnl_percent=Decimal("-7"),  # below mid-band threshold -6
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=False,
        ai_decision=None,
    )
    assert result == ClosePath.STOP_LOSS


def test_edge_case_current_pnl_equals_stop_at() -> None:
    """current_pnl_percent == stopAt should still close (boundary inclusive)."""
    pos = _base_position(
        trailing_peak_pnl_pct=Decimal("5"),  # arms L1 (trigger=5)
        cumulative_close_pct=Decimal("0"),
    )
    result = classify_close_path(
        position=pos,
        current_pnl_percent=Decimal("2"),  # exactly at L1.stop_at=2
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=True,
        ai_decision=None,
    )
    assert result == ClosePath.TRAILING_STOP


def test_all_stages_done_no_more_partial_profit() -> None:
    """When all stages are completed, partial_profit should not fire again."""
    pos = _base_position(
        trailing_peak_pnl_pct=Decimal("0"),
        cumulative_close_pct=Decimal("100"),  # all stages done
    )
    result = classify_close_path(
        position=pos,
        current_pnl_percent=Decimal("20"),  # high pnl but all stages done
        sl_params=_SL_PARAMS,
        trailing_levels=_TRAILING_LEVELS,
        partial_stages=_PARTIAL_STAGES,
        enable_code_level_protection=False,
        ai_decision=None,
    )
    assert result == ClosePath.NONE
