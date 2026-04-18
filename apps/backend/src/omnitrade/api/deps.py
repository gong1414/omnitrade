"""FastAPI dependency providers for Phase-5 routes.

The ``app.state.container`` is populated by ``main.create_app()`` during
the lifespan startup; every route pulls the services it needs through the
helpers below so tests can override one dependency at a time via
``app.dependency_overrides[...]``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.application.account_service import AccountService
from omnitrade.application.decision_service import DecisionService
from omnitrade.application.events.bus import EventBus
from omnitrade.application.position_manager import PositionManager
from omnitrade.application.rebate.service import RebateService
from omnitrade.application.risk_service import RiskService
from omnitrade.config import Settings, get_settings
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from omnitrade.observability.log_store import LogBuffer

if TYPE_CHECKING:
    from omnitrade.api.container import ApiContainer


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a managed ``AsyncSession`` bound to the app-scoped engine."""
    container = _get_container(request)
    session = container.session_factory()
    try:
        yield session
    finally:
        await session.close()


def _get_container(request: Request) -> ApiContainer:
    """Return the ``ApiContainer`` from ``app.state`` or 503 if missing."""
    container = getattr(request.app.state, "api_container", None)
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API container not initialised",
        )
    return cast("ApiContainer", container)


def get_container(request: Request) -> ApiContainer:
    """Expose the ``ApiContainer`` as a dependency (tests can override)."""
    return _get_container(request)


def get_account_service(
    container: ApiContainer = Depends(get_container),
) -> AccountService:
    return container.account_service


def get_position_manager(
    container: ApiContainer = Depends(get_container),
) -> PositionManager:
    return container.position_manager


def get_position_repository(
    container: ApiContainer = Depends(get_container),
) -> PositionRepository:
    return container.position_repo


def get_decision_service(
    container: ApiContainer = Depends(get_container),
) -> DecisionService:
    return container.decision_service


def get_rebate_service(
    container: ApiContainer = Depends(get_container),
) -> RebateService:
    return container.rebate_service


def get_risk_service(
    container: ApiContainer = Depends(get_container),
) -> RiskService:
    return container.risk_service


def get_event_bus(
    container: ApiContainer = Depends(get_container),
) -> EventBus:
    return container.event_bus


def get_trade_repository(
    container: ApiContainer = Depends(get_container),
) -> TradeRepository:
    return container.trade_repo


def get_account_history_repository(
    container: ApiContainer = Depends(get_container),
) -> AccountHistoryRepository:
    return container.account_history_repo


def get_exchange(
    container: ApiContainer = Depends(get_container),
) -> ExchangeClient:
    return container.exchange


def get_log_buffer(
    container: ApiContainer = Depends(get_container),
) -> LogBuffer:
    return container.log_buffer


def verify_manual_close_password(
    password: str,
    settings: Settings = Depends(get_settings),
) -> None:
    """401 if the pre-shared password does not match ``MANUAL_CLOSE_PASSWORD``.

    Empty / unset server-side value disables the endpoint (service-level 401).
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


__all__ = [
    "get_account_history_repository",
    "get_account_service",
    "get_container",
    "get_db_session",
    "get_decision_service",
    "get_event_bus",
    "get_exchange",
    "get_log_buffer",
    "get_position_manager",
    "get_position_repository",
    "get_rebate_service",
    "get_risk_service",
    "get_trade_repository",
    "verify_manual_close_password",
]
