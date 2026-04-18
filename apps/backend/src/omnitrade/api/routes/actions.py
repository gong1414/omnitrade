"""POST /api/v1/actions/close-position — password-gated manual close."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from omnitrade.api.deps import get_position_manager
from omnitrade.application.position_manager import PositionManager
from omnitrade.config import Settings, get_settings

router = APIRouter(tags=["actions"])


class CloseRequest(BaseModel):
    """Body for POST /actions/close-position."""

    symbol: str = Field(min_length=1, description="Trading symbol (e.g. BTC_USDT).")
    password: str = Field(min_length=1, description="Pre-shared manual-close password.")
    reason: str = Field(default="manual", description="Audit reason (default 'manual').")


def _check_password(password: str, settings: Settings) -> None:
    """401 unless ``password`` matches ``MANUAL_CLOSE_PASSWORD``.

    Empty/unset server-side value disables the endpoint entirely (401).
    """
    expected = settings.manual_close_password
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="manual close disabled (MANUAL_CLOSE_PASSWORD unset)",
        )
    if password != expected.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid password",
        )


@router.post("/actions/close-position")
async def close_position(
    body: CloseRequest,
    manager: PositionManager = Depends(get_position_manager),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Fully close ``symbol`` after validating the manual-close password."""
    _check_password(body.password, settings)
    trade = await manager.close_position(symbol=body.symbol, reason=body.reason)
    return {
        "order_id": trade.order_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": str(trade.quantity),
        "price": str(trade.price),
        "fee": str(trade.fee) if trade.fee is not None else None,
        "status": trade.status,
    }


__all__ = ["CloseRequest", "router"]
