"""Unit tests for ``application.signal_service.SignalService``."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.application.signal_service import SignalService
from omnitrade.domain.entities import TradingSignal


class _FakeSession:
    """Minimal ``AsyncSession`` double tracking commit/close + add calls."""

    def __init__(self) -> None:
        self.committed = False
        self.closed = False
        self.added_rows: list[Any] = []

    async def commit(self) -> None:
        self.committed = True

    async def close(self) -> None:
        self.closed = True

    async def flush(self) -> None:
        return None

    async def refresh(self, row: Any) -> None:
        return None

    def add(self, row: Any) -> None:
        self.added_rows.append(row)

    # Required for SignalRepository.create's signature which ultimately
    # uses add/flush/refresh — not exercised here since we mock the repo.


class _FakeRepo:
    """Tracks ``create`` calls; configurable to raise on Nth invocation."""

    def __init__(self, raise_on: int | None = None) -> None:
        self.calls: list[TradingSignal] = []
        self._raise_on = raise_on

    async def create(self, session: Any, sig: TradingSignal) -> TradingSignal:
        self.calls.append(sig)
        if self._raise_on is not None and len(self.calls) == self._raise_on:
            raise RuntimeError("induced failure")
        return sig


async def _session_factory(session: _FakeSession) -> _FakeSession:
    return session


def _make_ohlcv(n: int) -> list[list[float]]:
    return [[i * 60_000, 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n)]


@pytest.mark.asyncio
async def test_record_batch_empty_returns_zero() -> None:
    session = _FakeSession()
    repo = _FakeRepo()
    service = SignalService(
        repo=repo,  # type: ignore[arg-type]
        session_factory=lambda: _session_factory(session),
    )
    written = await service.record_batch({}, datetime.now(tz=UTC))
    assert written == 0
    assert not session.committed


@pytest.mark.asyncio
async def test_record_batch_success_writes_all_rows() -> None:
    session = _FakeSession()
    repo = _FakeRepo()
    service = SignalService(
        repo=repo,  # type: ignore[arg-type]
        session_factory=lambda: _session_factory(session),
    )
    ohlcv_per_symbol = {
        "BTC_USDT": _make_ohlcv(60),
        "ETH_USDT": _make_ohlcv(60),
    }
    written = await service.record_batch(ohlcv_per_symbol, datetime.now(tz=UTC))
    assert written == 2
    assert len(repo.calls) == 2
    assert {s.symbol for s in repo.calls} == {"BTC_USDT", "ETH_USDT"}
    assert session.committed is True
    assert session.closed is True


@pytest.mark.asyncio
async def test_record_batch_swallows_repo_failure_returns_zero() -> None:
    session = _FakeSession()
    # Raise on first create → full batch aborts.
    repo = _FakeRepo(raise_on=1)
    service = SignalService(
        repo=repo,  # type: ignore[arg-type]
        session_factory=lambda: _session_factory(session),
    )
    written = await service.record_batch(
        {"BTC_USDT": _make_ohlcv(60)}, datetime.now(tz=UTC)
    )
    # Plan v3 MF-6: failure is swallowed, return 0; cycle must continue.
    assert written == 0
    # Session is still closed by the outer finally (exception path).
    assert session.closed is True


@pytest.mark.asyncio
async def test_record_batch_signal_shape() -> None:
    session = _FakeSession()
    repo = _FakeRepo()
    service = SignalService(
        repo=repo,  # type: ignore[arg-type]
        session_factory=lambda: _session_factory(session),
    )
    await service.record_batch(
        {"BTC_USDT": _make_ohlcv(60)}, datetime.now(tz=UTC)
    )
    assert len(repo.calls) == 1
    sig = repo.calls[0]
    assert sig.symbol == "BTC_USDT"
    # Last close from _make_ohlcv is 1.5.
    assert sig.price == Decimal("1.5")
