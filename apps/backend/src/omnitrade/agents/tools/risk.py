"""Risk-calculation tool — sizes a position against the strategy's leverage band.

Thin wrapper over ``domain.services.leverage_bands.get_leverage_band``.
No extra abstraction layer (plan v3 MAJOR-6 rejected one).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.domain.enums import StrategyName
from omnitrade.domain.services.leverage_bands import get_leverage_band
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


_VALID_STRATEGIES: frozenset[str] = frozenset({s.value for s in StrategyName})


class CalculateRiskArgs(BaseModel):
    strategy: str = Field(
        description=(
            "Strategy name (one of: arena-guardian, arena-steward, arena-raider, "
            "arena-raider-squad, arena-scalper, arena-swingsmith, arena-strider, "
            "arena-rebate-hunter, arena-autopilot, arena-dual-signal, arena-tribunal)."
        ),
    )
    max_leverage: int = Field(
        ge=1, le=125, description="System-wide leverage ceiling (e.g. 25)."
    )
    account_equity: Decimal = Field(
        gt=Decimal(0), description="Total account equity in USDT."
    )
    confidence: Decimal = Field(
        ge=Decimal(0), le=Decimal(1), description="Decision confidence in [0, 1]."
    )


def build_calculate_risk_tool() -> StructuredTool:
    async def _calculate_risk(
        strategy: str,
        max_leverage: int,
        account_equity: Decimal,
        confidence: Decimal,
    ) -> dict[str, Any]:
        with_context(logger).debug(
            "tool.calculate_risk",
            strategy=strategy,
            max_leverage=max_leverage,
            equity=str(account_equity),
            confidence=str(confidence),
        )
        if strategy not in _VALID_STRATEGIES:
            return {
                "error": f"unknown strategy {strategy!r}",
                "valid": sorted(_VALID_STRATEGIES),
            }
        strat_enum = StrategyName(strategy)
        min_lev, max_lev = get_leverage_band(strat_enum, max_leverage)
        # Interpolate leverage inside the band by confidence.
        leverage = round(min_lev + (max_lev - min_lev) * float(confidence))
        # Risk budget: up to 2% of equity at confidence=1, linear from 0.
        risk_fraction = confidence * Decimal("0.02")
        max_loss_usdt = account_equity * risk_fraction
        # Position notional ~ equity * leverage * (risk_fraction / risk_fraction) —
        # the LLM receives enough primitives to reason about sizing.
        position_notional_usdt = account_equity * Decimal(leverage) * risk_fraction
        return {
            "strategy": strategy,
            "leverage_band": {"min": min_lev, "max": max_lev},
            "suggested_leverage": leverage,
            "max_loss_usdt": str(max_loss_usdt),
            "position_notional_usdt": str(position_notional_usdt),
            "risk_fraction": str(risk_fraction),
        }

    return StructuredTool.from_function(
        coroutine=_calculate_risk,
        name="calculateRisk",
        description=(
            "Compute the leverage band + max-loss + position-notional budget "
            "for a prospective trade given strategy, max_leverage, account "
            "equity, and confidence [0,1]. Returns the strategy's (min,max) "
            "leverage band, a confidence-interpolated suggested leverage, "
            "and USDT-denominated risk budgets."
        ),
        args_schema=CalculateRiskArgs,
    )


__all__ = ["CalculateRiskArgs", "build_calculate_risk_tool"]
