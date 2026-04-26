"""Schedule-registration helper unit tests.

Covers :func:`omnitrade.main._cron_for_interval` (cron emission) and
:func:`omnitrade.main._register_agentos_trading_schedule`'s
idempotency contract — re-registering with the same name updates the
existing schedule rather than creating a duplicate.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from pydantic import SecretStr

import omnitrade.config as cfg
import omnitrade.main as main_mod
from omnitrade.api.agent_os_app import MonitorHolder

Settings = cfg.Settings
_cron_for_interval = main_mod._cron_for_interval
_register_agentos_trading_schedule = main_mod._register_agentos_trading_schedule
lifespan = main_mod.lifespan


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (1, "*/1 * * * *"),
        (15, "*/15 * * * *"),
        (59, "*/59 * * * *"),
        (60, "0 */1 * * *"),
        (120, "0 */2 * * *"),
        (1440, "0 0 * * *"),
        (90, "0 */1 * * *"),  # Non-aligned — clamps to nearest hour
    ],
)
def test_cron_for_interval(minutes: int, expected: str) -> None:
    assert _cron_for_interval(minutes) == expected


def test_cron_for_interval_invalid_falls_back() -> None:
    assert _cron_for_interval(0) == "*/20 * * * *"
    assert _cron_for_interval(-5) == "*/20 * * * *"


@pytest.mark.asyncio
async def test_register_schedule_uses_shared_db_and_does_not_close_it() -> None:
    """When a shared PostgresDb is supplied, the helper must NOT close
    it — that DB belongs to AgentOS and is closed at app shutdown.
    """
    settings = Settings(
        agno_postgres_url="postgresql+psycopg://x:x@x:5432/x",
        trading_interval_minutes=15,
        cycle_trigger_timeout_seconds=60,
    )
    shared_db = MagicMock()
    shared_db.close = MagicMock()

    fake_schedule = MagicMock(id="sched-1", enabled=True)
    fake_manager = MagicMock()
    fake_manager.acreate = AsyncMock(return_value=fake_schedule)
    fake_manager.aenable = AsyncMock(return_value=fake_schedule)

    with patch(
        "agno.scheduler.manager.ScheduleManager",
        return_value=fake_manager,
    ) as manager_cls:
        await _register_agentos_trading_schedule(settings, shared_db=shared_db)

    manager_cls.assert_called_once_with(db=shared_db)
    fake_manager.acreate.assert_awaited_once()
    call_kwargs = fake_manager.acreate.await_args.kwargs
    assert call_kwargs["name"] == "trading-cycle"
    assert call_kwargs["cron"] == "*/15 * * * *"
    assert call_kwargs["endpoint"] == "/workflows/trading-cycle/runs"
    assert call_kwargs["if_exists"] == "update"
    # Already enabled — aenable should not be called.
    fake_manager.aenable.assert_not_called()
    # Critically: we must NOT have closed the shared db.
    shared_db.close.assert_not_called()


@pytest.mark.asyncio
async def test_register_schedule_enables_when_disabled() -> None:
    """If the existing row is disabled (e.g. left over from a previous
    deployment that toggled it off), bootstrap re-enables it."""
    settings = Settings(
        agno_postgres_url="postgresql+psycopg://x:x@x:5432/x",
        trading_interval_minutes=20,
        cycle_trigger_timeout_seconds=60,
    )
    shared_db = MagicMock()
    fake_schedule = MagicMock(id="sched-2", enabled=False)
    fake_manager = MagicMock()
    fake_manager.acreate = AsyncMock(return_value=fake_schedule)
    fake_manager.aenable = AsyncMock(return_value=fake_schedule)

    with patch(
        "agno.scheduler.manager.ScheduleManager",
        return_value=fake_manager,
    ):
        await _register_agentos_trading_schedule(settings, shared_db=shared_db)

    fake_manager.aenable.assert_awaited_once_with("sched-2")


@pytest.mark.asyncio
async def test_register_schedule_closes_owned_db() -> None:
    """When no shared db is provided the helper opens its own and must
    close it on the way out (review issue #1 — connection leak)."""
    settings = Settings(
        agno_postgres_url="postgresql+psycopg://x:x@x:5432/x",
        trading_interval_minutes=10,
        cycle_trigger_timeout_seconds=60,
    )
    own_db = MagicMock()
    own_db.close = MagicMock()
    fake_schedule = MagicMock(id="sched-3", enabled=True)
    fake_manager = MagicMock()
    fake_manager.acreate = AsyncMock(return_value=fake_schedule)
    fake_manager.aenable = AsyncMock(return_value=fake_schedule)

    with (
        patch(
            "agno.db.postgres.PostgresDb",
            return_value=own_db,
        ),
        patch(
            "agno.scheduler.manager.ScheduleManager",
            return_value=fake_manager,
        ),
    ):
        await _register_agentos_trading_schedule(settings, shared_db=None)

    own_db.close.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_builds_agentos_monitor_before_schedule_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentOS-driven cycles must have a bound monitor before cron registration."""
    app = FastAPI()
    app.state.api_container = object()
    holder = MonitorHolder()
    app.state.agent_os_monitor_holder = holder

    settings = Settings(
        llm_api_key=SecretStr("test-key"),
        agno_postgres_url="postgresql+psycopg://x:x@x:5432/x",
        agno_scheduler_drives_cycle=True,
        scheduler_enabled=False,
    )
    monkeypatch.setattr(cfg, "_settings", settings)

    events: list[str] = []
    fake_monitor = object()

    def _fake_ensure_trading_monitor(
        app_arg: FastAPI,
        settings_arg: Settings,
        container_arg: object,
        *,
        driver: str,
    ) -> object:
        assert app_arg is app
        assert settings_arg is settings
        assert container_arg is app.state.api_container
        assert driver == "agentos"
        events.append("build")
        app_arg.state.trading_monitor = fake_monitor
        return fake_monitor

    async def _fake_register_schedule(
        settings_arg: Settings,
        *,
        shared_db: Any | None = None,
    ) -> None:
        assert settings_arg is settings
        assert shared_db is None
        assert holder.get_monitor() is fake_monitor
        events.append("register")

    monkeypatch.setattr(main_mod, "_ensure_trading_monitor", _fake_ensure_trading_monitor)
    monkeypatch.setattr(main_mod, "_register_agentos_trading_schedule", _fake_register_schedule)

    async with lifespan(app):
        pass

    assert events == ["build", "register"]
