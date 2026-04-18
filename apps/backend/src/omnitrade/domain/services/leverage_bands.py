"""Leverage band calculator — pure function, no I/O.

Maps strategy names to (min_leverage, max_leverage) tuples based on MAX_LEVERAGE.

Formula per strategy:
  arena-guardian:  min=ceil(0.1*L) or 2, max=ceil(0.3*L) or 4
  arena-steward:      min=ceil(0.3*L) or 3, max=ceil(0.6*L) or 8
  arena-raider:    min=ceil(0.6*L) or 8, max=L or 15
  arena-scalper:   min=ceil(0.5*L) or 3, max=ceil(0.75*L) or 5
  arena-swingsmith:   min=ceil(0.2*L) or 2, max=ceil(0.5*L) or 5
  arena-strider:   min=ceil(0.1*L) or 2, max=ceil(0.3*L) or 5
  arena-rebate-hunter: low band (same as arena-guardian)
  arena-autopilot: min=L, max=L  (full leverage)
  arena-dual-signal:    min=L, max=L  (full leverage)
  arena-raider-squad: high band, team-led (same as arena-raider)
  arena-tribunal: arena-steward band
"""

from __future__ import annotations

import math

from omnitrade.domain.enums import StrategyName


def get_leverage_band(strategy: StrategyName, max_leverage: int) -> tuple[int, int]:
    """Return (min_leverage, max_leverage) for the given strategy and max leverage cap.

    Args:
        strategy: The trading strategy name.
        max_leverage: The system maximum leverage (e.g. 25).

    Returns:
        Tuple of (min_lev, max_lev), both in [1, max_leverage].
    """
    max_lev = max_leverage

    match strategy:
        case StrategyName.CONSERVATIVE:
            return (max(math.ceil(0.1 * max_lev), 2), max(math.ceil(0.3 * max_lev), 4))
        case StrategyName.BALANCED:
            return (max(math.ceil(0.3 * max_lev), 3), max(math.ceil(0.6 * max_lev), 8))
        case StrategyName.AGGRESSIVE:
            return (max(math.ceil(0.6 * max_lev), 8), max(max_lev, 15))
        case StrategyName.AGGRESSIVE_TEAM:
            # team-led arena-raider
            return (max(math.ceil(0.6 * max_lev), 8), max(max_lev, 15))
        case StrategyName.ULTRA_SHORT:
            return (max(math.ceil(0.5 * max_lev), 3), max(math.ceil(0.75 * max_lev), 5))
        case StrategyName.SWING_TREND:
            return (max(math.ceil(0.2 * max_lev), 2), max(math.ceil(0.5 * max_lev), 5))
        case StrategyName.MEDIUM_LONG:
            return (max(math.ceil(0.1 * max_lev), 2), max(math.ceil(0.3 * max_lev), 5))
        case StrategyName.REBATE_FARMING:
            # low band, same as arena-guardian
            return (max(math.ceil(0.1 * max_lev), 2), max(math.ceil(0.3 * max_lev), 4))
        case StrategyName.AI_AUTONOMOUS:
            # full leverage
            return (max_lev, max_lev)
        case StrategyName.ALPHA_BETA:
            # full leverage (code-level default)
            return (max_lev, max_lev)
        case StrategyName.MULTI_AGENT_CONSENSUS:
            # arena-steward band
            return (max(math.ceil(0.3 * max_lev), 3), max(math.ceil(0.6 * max_lev), 8))
