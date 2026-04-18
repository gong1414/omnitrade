"""Tests for three-way state helper — confirms immutability and atomic contract."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.domain.entities import Position
from omnitrade.domain.services.three_way_state import (
    apply_three_way_state,
    get_profit_protection_stop_percent,
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


class TestApplyThreeWayState:
    def test_returns_new_instance(self) -> None:
        pos = _base_position()
        updated = apply_three_way_state(pos, Decimal("30"), Decimal("2"), Decimal("8"))
        assert updated is not pos

    def test_three_fields_updated(self) -> None:
        pos = _base_position()
        updated = apply_three_way_state(
            pos,
            new_cumulative_close_pct=Decimal("30"),
            new_stop_loss=Decimal("2"),
            new_trailing_peak=Decimal("8"),
        )
        assert updated.cumulative_close_pct == Decimal("30")
        assert updated.stop_loss == Decimal("2")
        assert updated.trailing_peak_pnl_pct == Decimal("8")

    def test_only_three_fields_change(self) -> None:
        pos = _base_position(quantity=Decimal("5"), leverage=20, side="short")
        updated = apply_three_way_state(
            pos,
            new_cumulative_close_pct=Decimal("60"),
            new_stop_loss=Decimal("4"),
            new_trailing_peak=Decimal("12"),
        )
        # All other fields must remain unchanged
        assert updated.symbol == pos.symbol
        assert updated.quantity == pos.quantity
        assert updated.leverage == pos.leverage
        assert updated.side == pos.side
        assert updated.entry_price == pos.entry_price
        assert updated.entry_order_id == pos.entry_order_id
        assert updated.opened_at == pos.opened_at

    def test_stop_loss_can_be_cleared(self) -> None:
        pos = _base_position(stop_loss=Decimal("3"))
        updated = apply_three_way_state(pos, Decimal("30"), None, Decimal("8"))
        assert updated.stop_loss is None

    def test_original_unchanged_after_update(self) -> None:
        pos = _base_position(
            cumulative_close_pct=Decimal("0"),
            stop_loss=None,
            trailing_peak_pnl_pct=Decimal("0"),
        )
        _ = apply_three_way_state(pos, Decimal("30"), Decimal("3"), Decimal("9"))
        # Original must be completely unchanged
        assert pos.cumulative_close_pct == Decimal("0")
        assert pos.stop_loss is None
        assert pos.trailing_peak_pnl_pct == Decimal("0")

    def test_idempotent_double_apply(self) -> None:
        pos = _base_position()
        first = apply_three_way_state(pos, Decimal("30"), Decimal("2"), Decimal("8"))
        second = apply_three_way_state(first, Decimal("30"), Decimal("2"), Decimal("8"))
        assert first == second


class TestGetProfitProtectionStopPercent:
    def test_stage_0_returns_half_trigger(self) -> None:
        result = get_profit_protection_stop_percent(Decimal("8"), stage_index=0)
        assert result == Decimal("4.0")

    def test_stage_1_returns_60_percent(self) -> None:
        result = get_profit_protection_stop_percent(Decimal("12"), stage_index=1)
        assert result == Decimal("7.2")

    def test_stage_2_returns_70_percent(self) -> None:
        result = get_profit_protection_stop_percent(Decimal("18"), stage_index=2)
        assert result == Decimal("12.6")

    def test_stage_index_clamped_at_2(self) -> None:
        r2 = get_profit_protection_stop_percent(Decimal("10"), stage_index=2)
        r3 = get_profit_protection_stop_percent(Decimal("10"), stage_index=3)
        assert r2 == r3  # clamped

    def test_positive_result_for_positive_trigger(self) -> None:
        for stage_idx in range(3):
            result = get_profit_protection_stop_percent(Decimal("10"), stage_index=stage_idx)
            assert result > Decimal("0")

    @pytest.mark.parametrize(
        "trigger,stage,expected",
        [
            (Decimal("8"), 0, Decimal("4.0")),
            (Decimal("12"), 1, Decimal("7.2")),
            (Decimal("18"), 2, Decimal("12.6")),
        ],
    )
    def test_parametrized_stages(self, trigger: Decimal, stage: int, expected: Decimal) -> None:
        result = get_profit_protection_stop_percent(trigger, stage_index=stage)
        assert result == expected
