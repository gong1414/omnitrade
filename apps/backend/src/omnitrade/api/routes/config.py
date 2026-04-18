"""GET /api/v1/config — non-secret runtime configuration.

This endpoint MUST NEVER expose ``SecretStr`` fields (API keys, manual-close
password). The allow-list below is explicit to force a code review whenever
a new field is surfaced to the dashboard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from omnitrade.config import Settings, get_settings

router = APIRouter(tags=["config"])


_ALLOWED_FIELDS: tuple[str, ...] = (
    "trading_strategy",
    "trading_interval_minutes",
    "max_leverage",
    "max_positions",
    "max_holding_hours",
    "extreme_stop_loss_percent",
    "initial_balance_usdt",
    "account_stop_loss_usdt",
    "account_take_profit_usdt",
    "account_record_interval_minutes",
    "account_drawdown_warning_percent",
    "account_drawdown_no_new_position_percent",
    "account_drawdown_force_close_percent",
    "exchange",
    "gate_use_testnet",
    "okx_use_testnet",
    "llm_provider",
    "llm_model_name",
    "fee_rebate_percent",
    "environment",
    "log_level",
    "exchange_fee_rate",
)


@router.get("/config")
async def get_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return the non-secret configuration subset."""
    out: dict[str, Any] = {}
    for field in _ALLOWED_FIELDS:
        value = getattr(settings, field, None)
        # Pydantic AnyHttpUrl → string
        if value is not None and not isinstance(value, int | float | bool | str):
            value = str(value)
        out[field] = value
    return out


__all__ = ["router"]
