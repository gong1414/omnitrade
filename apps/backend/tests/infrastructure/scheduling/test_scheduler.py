"""Scheduler tests — confirm 5 jobs are registered with correct intervals.

Verifies graceful shutdown and that all loop names are present.
All tests are async because AsyncIOScheduler requires a running event loop.
"""

from __future__ import annotations

import asyncio

import pytest

from omnitrade.infrastructure.scheduling import loop_registry
from omnitrade.infrastructure.scheduling.scheduler import OmniScheduler


def _fresh_registry() -> None:
    """Clear the module-level registry before each test."""
    loop_registry._registry.clear()


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    _fresh_registry()
    yield
    _fresh_registry()


async def test_five_jobs_registered_after_start() -> None:
    """Exactly 5 jobs must be registered (consensus §7 R1 — none folded)."""
    scheduler = OmniScheduler(
        trading_interval_minutes=20,
        account_record_interval_minutes=1,
    )
    scheduler.start()
    try:
        jobs = scheduler.get_jobs()
        assert len(jobs) == 5
        job_ids = {j["id"] for j in jobs}
        assert job_ids == {
            "trading_loop",
            "trailing_stop_loop",
            "partial_profit_loop",
            "account_recorder_loop",
            "news_fetch_loop",
        }
    finally:
        scheduler.stop(wait=False)


async def test_trading_loop_interval_correct() -> None:
    """trading_loop must fire every 20 minutes (1200 seconds) by default."""
    scheduler = OmniScheduler(trading_interval_minutes=20)
    scheduler.start()
    try:
        spec = loop_registry.get("trading_loop")
        assert spec is not None
        assert spec.interval_seconds == 20 * 60
    finally:
        scheduler.stop(wait=False)


async def test_trailing_stop_interval_10s() -> None:
    scheduler = OmniScheduler()
    scheduler.start()
    try:
        spec = loop_registry.get("trailing_stop_loop")
        assert spec is not None
        assert spec.interval_seconds == 10
    finally:
        scheduler.stop(wait=False)


async def test_partial_profit_interval_10s() -> None:
    """partial_profit_loop must have its OWN 10s interval (NOT folded)."""
    scheduler = OmniScheduler()
    scheduler.start()
    try:
        spec = loop_registry.get("partial_profit_loop")
        assert spec is not None
        assert spec.interval_seconds == 10
    finally:
        scheduler.stop(wait=False)


async def test_account_recorder_interval_1min() -> None:
    scheduler = OmniScheduler(account_record_interval_minutes=1)
    scheduler.start()
    try:
        spec = loop_registry.get("account_recorder_loop")
        assert spec is not None
        assert spec.interval_seconds == 60
    finally:
        scheduler.stop(wait=False)


async def test_news_fetch_interval_5min() -> None:
    """news_fetch_loop must fire every 5 minutes per scheduledNewsService.ts."""
    scheduler = OmniScheduler()
    scheduler.start()
    try:
        spec = loop_registry.get("news_fetch_loop")
        assert spec is not None
        assert spec.interval_seconds == 300
    finally:
        scheduler.stop(wait=False)


async def test_graceful_shutdown() -> None:
    """stop() must not raise. is_running transitions from True to False."""
    scheduler = OmniScheduler()
    scheduler.start()
    assert scheduler.is_running is True
    scheduler.stop(wait=False)
    # Give the event loop one tick to process the shutdown
    await asyncio.sleep(0.05)
    assert scheduler.is_running is False


async def test_custom_trading_interval() -> None:
    """trading_interval_minutes is configurable."""
    scheduler = OmniScheduler(trading_interval_minutes=30)
    scheduler.start()
    try:
        spec = loop_registry.get("trading_loop")
        assert spec is not None
        assert spec.interval_seconds == 30 * 60
    finally:
        scheduler.stop(wait=False)


async def test_loop_registry_get_all() -> None:
    """get_all() returns all 5 registered specs."""
    scheduler = OmniScheduler()
    scheduler.start()
    try:
        all_specs = loop_registry.get_all()
        assert len(all_specs) == 5
    finally:
        scheduler.stop(wait=False)
