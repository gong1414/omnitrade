"""GET /api/v1/account — most-recent account snapshot + peak + drawdown."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from omnitrade.api.deps import get_account_service
from omnitrade.application.account_service import AccountService

router = APIRouter(tags=["account"])


@router.get("/account")
async def get_account(
    service: AccountService = Depends(get_account_service),
) -> dict[str, Any]:
    """Return the latest account snapshot with peak + drawdown.

    When no history rows exist the service derives the snapshot from a live
    balance fetch so the UI has something to render on a fresh install.
    """
    return await service.current_snapshot()


__all__ = ["router"]
