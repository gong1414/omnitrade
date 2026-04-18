"""Shared fixtures for ``tests/api/**`` — builds a real FastAPI app with an
in-memory SQLite database and a fake exchange, attached via
``app.state.api_container``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from omnitrade.api.container import build_api_container
from omnitrade.config import Settings
from omnitrade.domain.entities import AccountSnapshot
from omnitrade.main import create_app
from tests.application._fakes import FakeExchange, build_sqlite_session_factory, make_trade


@pytest.fixture(autouse=True)
def _reset_settings_singleton(monkeypatch):  # type: ignore[no-untyped-def]
    """Keep per-test environment clean of the cached Settings singleton."""
    import omnitrade.config as cfg

    monkeypatch.setattr(cfg, "_settings", None)
    yield
    monkeypatch.setattr(cfg, "_settings", None)


@pytest.fixture
async def api_settings(monkeypatch):  # type: ignore[no-untyped-def]
    """Test-scoped ``Settings`` with the manual-close password configured."""
    monkeypatch.setenv("MANUAL_CLOSE_PASSWORD", "s3cret")
    monkeypatch.setenv("ENVIRONMENT", "testnet")
    # Force a fresh load honouring the above env overrides.
    return Settings()


@pytest.fixture
async def api_app(api_settings):  # type: ignore[no-untyped-def]
    """Build an app with a container wired to in-memory SQLite + FakeExchange."""
    _factory, open_session = await build_sqlite_session_factory()

    fake_balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1234.5"),
        available_cash=Decimal("1000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    exchange = FakeExchange(
        balance=fake_balance,
        positions=[],
        close_trade=make_trade(order_id="close-1", ttype="close"),
    )

    # Monkey-patch get_settings() so deps see our test settings.
    import omnitrade.config as cfg

    cfg._settings = api_settings

    container = build_api_container(
        settings=api_settings,
        exchange=exchange,  # type: ignore[arg-type]
        session_factory=_factory,
    )
    # Override open_session to reuse the shared in-memory engine.
    container.open_session = open_session  # type: ignore[assignment]
    container.account_service._session_factory = open_session  # type: ignore[attr-defined]
    container.decision_service._session_factory = open_session  # type: ignore[attr-defined]
    container.position_manager._session_factory = open_session  # type: ignore[attr-defined]
    container.rebate_service._session_factory = open_session  # type: ignore[attr-defined]

    app = create_app(settings=api_settings)
    app.state.api_container = container
    app.state.test_exchange = exchange
    app.state.test_session_factory = open_session
    return app


@pytest.fixture
async def api_client(api_app) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[no-untyped-def]
    """AsyncClient pointed at the wired app (no network)."""
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


__all__ = []
