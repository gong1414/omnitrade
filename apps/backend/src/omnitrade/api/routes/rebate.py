"""GET /api/v1/rebate — 24-hour fee-rebate summary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from omnitrade.api.deps import get_rebate_service
from omnitrade.application.rebate.service import RebateService

router = APIRouter(tags=["rebate"])


@router.get("/rebate")
async def get_rebate_summary(
    service: RebateService = Depends(get_rebate_service),
) -> dict[str, Any]:
    """Return the rolling 24-hour rebate window summary."""
    summary = await service.compute_summary()
    return {
        "window_start": summary.window.start.isoformat(),
        "window_end": summary.window.end.isoformat(),
        "fee_rebate_percent": str(summary.fee_rebate_percent),
        "close_trades_count": summary.close_trades_count,
        "total_fees_usdt": str(summary.total_fees_usdt),
        "rebate_amount_usdt": str(summary.rebate_amount_usdt),
    }


__all__ = ["router"]
