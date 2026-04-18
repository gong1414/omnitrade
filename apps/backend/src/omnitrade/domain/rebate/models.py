"""Domain models for fee-rebate accounting.

Pure Pydantic value objects — no infra/app imports so the grep gate
``rg -n 'from omnitrade\\.(infrastructure|application|agents|api)'
apps/backend/src/omnitrade/domain/`` stays empty.

The 24-hour rebate window is defined as:

    rebate_amount = SUM(fee WHERE type='close' AND timestamp >= now - 24h)
                    * fee_rebate_percent / 100
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class RebateWindow(BaseModel):
    """Immutable [start, end] time window bounding a rebate calculation."""

    start: datetime
    end: datetime

    model_config = {"frozen": True}

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: datetime, info: object) -> datetime:
        start = getattr(info, "data", {}).get("start")
        if start is not None and v < start:
            raise ValueError(f"RebateWindow.end {v} precedes start {start}")
        return v

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


class RebateSummary(BaseModel):
    """Result of a single rebate calculation over a ``RebateWindow``."""

    window: RebateWindow
    fee_rebate_percent: Decimal
    close_trades_count: int
    total_fees_usdt: Decimal
    rebate_amount_usdt: Decimal

    model_config = {"frozen": True}

    @field_validator("fee_rebate_percent")
    @classmethod
    def percent_in_range(cls, v: Decimal) -> Decimal:
        if not (Decimal(0) <= v <= Decimal(100)):
            raise ValueError(f"fee_rebate_percent must be in [0, 100], got {v}")
        return v

    @field_validator("close_trades_count")
    @classmethod
    def count_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"close_trades_count must be >= 0, got {v}")
        return v


__all__ = ["RebateSummary", "RebateWindow"]
