"""Pure strategy→timeframes mapping (consensus plan §5 Phase 8.1).

No I/O, no async, no exchange calls — just a total function from
``StrategyName`` to an ordered ``list[str]`` of ccxt timeframe labels.
"""

from __future__ import annotations

from omnitrade.domain.enums import StrategyName

_ULTRA_SHORT_TFS: tuple[str, ...] = ("1m", "3m", "5m", "15m")
_SWING_TREND_TFS: tuple[str, ...] = ("15m", "1h", "4h", "1d")
_DEFAULT_TFS: tuple[str, ...] = ("5m", "15m", "1h")

_STRATEGY_TFS: dict[StrategyName, tuple[str, ...]] = {
    StrategyName.ULTRA_SHORT: _ULTRA_SHORT_TFS,
    StrategyName.REBATE_FARMING: _ULTRA_SHORT_TFS,
    StrategyName.SWING_TREND: _SWING_TREND_TFS,
}


def timeframes_for(strategy: StrategyName) -> list[str]:
    """Return the canonical timeframe set for ``strategy``.

    * ``ULTRA_SHORT`` / ``REBATE_FARMING`` → ``["1m", "3m", "5m", "15m"]``
    * ``SWING_TREND``                      → ``["15m", "1h", "4h", "1d"]``
    * all others                           → ``["5m", "15m", "1h"]``
    """
    return list(_STRATEGY_TFS.get(strategy, _DEFAULT_TFS))


__all__ = ["timeframes_for"]
