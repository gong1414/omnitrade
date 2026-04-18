"""Unit tests for ``domain.services.tf_strategy_map``."""

from __future__ import annotations

import pytest

from omnitrade.domain.enums import StrategyName
from omnitrade.domain.services.tf_strategy_map import timeframes_for


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        (StrategyName.ULTRA_SHORT, ["1m", "3m", "5m", "15m"]),
        (StrategyName.REBATE_FARMING, ["1m", "3m", "5m", "15m"]),
        (StrategyName.SWING_TREND, ["15m", "1h", "4h", "1d"]),
    ],
)
def test_explicit_strategy_mapping(strategy: StrategyName, expected: list[str]) -> None:
    assert timeframes_for(strategy) == expected


@pytest.mark.parametrize(
    "strategy",
    [
        s
        for s in StrategyName
        if s
        not in {
            StrategyName.ULTRA_SHORT,
            StrategyName.REBATE_FARMING,
            StrategyName.SWING_TREND,
        }
    ],
)
def test_default_fallback(strategy: StrategyName) -> None:
    assert timeframes_for(strategy) == ["5m", "15m", "1h"]


def test_returns_new_list_each_call() -> None:
    """The function must not leak the internal tuple so callers can mutate freely."""
    a = timeframes_for(StrategyName.SWING_TREND)
    b = timeframes_for(StrategyName.SWING_TREND)
    assert a == b
    a.append("zzz")
    assert b == ["15m", "1h", "4h", "1d"]
