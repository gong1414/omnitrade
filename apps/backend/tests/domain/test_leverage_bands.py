"""Tests for leverage band calculator."""

from __future__ import annotations

import pytest

from omnitrade.domain.enums import StrategyName
from omnitrade.domain.services.leverage_bands import get_leverage_band


@pytest.mark.parametrize(
    "strategy,max_lev,expected_min,expected_max",
    [
        # arena-guardian: ceil(0.1*25)=3≥2, ceil(0.3*25)=8≥4
        (StrategyName.CONSERVATIVE, 25, 3, 8),
        # arena-steward: ceil(0.3*25)=8≥3, ceil(0.6*25)=15≥8
        (StrategyName.BALANCED, 25, 8, 15),
        # arena-raider: ceil(0.6*25)=15≥8, max(25,15)=25
        (StrategyName.AGGRESSIVE, 25, 15, 25),
        # arena-raider-squad: same as arena-raider
        (StrategyName.AGGRESSIVE_TEAM, 25, 15, 25),
        # arena-scalper: ceil(0.5*25)=13≥3, ceil(0.75*25)=19≥5
        (StrategyName.ULTRA_SHORT, 25, 13, 19),
        # arena-swingsmith: ceil(0.2*25)=5≥2, ceil(0.5*25)=13≥5
        (StrategyName.SWING_TREND, 25, 5, 13),
        # arena-strider: ceil(0.1*25)=3≥2, ceil(0.3*25)=8≥5
        (StrategyName.MEDIUM_LONG, 25, 3, 8),
        # arena-rebate-hunter: same as arena-guardian
        (StrategyName.REBATE_FARMING, 25, 3, 8),
        # arena-autopilot: full leverage
        (StrategyName.AI_AUTONOMOUS, 25, 25, 25),
        # arena-dual-signal: full leverage
        (StrategyName.ALPHA_BETA, 25, 25, 25),
        # arena-tribunal: arena-steward band
        (StrategyName.MULTI_AGENT_CONSENSUS, 25, 8, 15),
        # small max leverage (edge: floors kick in)
        (StrategyName.CONSERVATIVE, 5, 2, 4),
        (StrategyName.BALANCED, 5, 3, 8),
        (StrategyName.AGGRESSIVE, 5, 8, 15),
    ],
)
def test_get_leverage_band(
    strategy: StrategyName, max_lev: int, expected_min: int, expected_max: int
) -> None:
    min_lev, max_l = get_leverage_band(strategy, max_lev)
    assert min_lev == expected_min, f"{strategy}: expected min {expected_min}, got {min_lev}"
    assert max_l == expected_max, f"{strategy}: expected max {expected_max}, got {max_l}"


def test_min_lte_max_for_all_strategies() -> None:
    """min_leverage <= max_leverage for all strategies at all common max_leverage values."""
    for max_lev in [5, 10, 20, 25, 50, 100, 125]:
        for strategy in StrategyName:
            min_l, max_l = get_leverage_band(strategy, max_lev)
            assert min_l <= max_l, f"{strategy} at max_lev={max_lev}: min={min_l} > max={max_l}"


def test_all_strategies_covered() -> None:
    """Every StrategyName member returns a valid band (no missing match arms)."""
    for strategy in StrategyName:
        band = get_leverage_band(strategy, 25)
        assert band is not None
        assert len(band) == 2
