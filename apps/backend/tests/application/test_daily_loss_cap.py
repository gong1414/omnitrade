"""PR-D Phase D3 — DailyLossLimiter + risk_check integration tests.

Confirms:
  - zero loss / small loss allows action through
  - loss at the cap threshold does NOT override (strict less-than)
  - loss exceeding cap forces action=hold
  - hold decisions always pass through (cap never forces action)
  - limiter exception is non-fatal — decision passes through on failure
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnitrade.application.composition import _build_risk_check_fn
from omnitrade.application.risk_service import DailyLossCap, DailyLossLimiter
from omnitrade.domain.entities import Decision


def _make_decision(action: str = "open", symbol: str = "BTC_USDT") -> Decision:
    return Decision(
        action=action,
        symbol=symbol if action != "hold" else None,
        side="long" if action != "hold" else None,
        size=Decimal("0.01") if action != "hold" else None,
        leverage=5 if action != "hold" else None,
        confidence=Decimal("0.75"),
        reasoning="test",
    )


def _fake_container(realized_pnl: Decimal) -> MagicMock:
    """Build a fake container whose trade_repo returns `realized_pnl`."""
    container = MagicMock()
    container.trade_repo.realized_pnl_since = AsyncMock(return_value=realized_pnl)
    session = MagicMock()
    session.close = AsyncMock()
    container.open_session = AsyncMock(return_value=session)
    return container


def _fake_settings(cap_usdt: float = 100.0) -> MagicMock:
    s = MagicMock()
    s.daily_loss_cap_usdt = cap_usdt
    return s


@pytest.mark.asyncio
async def test_no_loss_allows_action() -> None:
    container = _fake_container(Decimal("0"))
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    decision = _make_decision("open")
    result = await risk_check(decision, [])
    assert result.action == "open"


@pytest.mark.asyncio
async def test_small_loss_allows_action() -> None:
    container = _fake_container(Decimal("-50"))
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    result = await risk_check(_make_decision("open"), [])
    assert result.action == "open"


@pytest.mark.asyncio
async def test_loss_at_threshold_boundary_allows_action() -> None:
    # Cap = 100, loss = 100 → limiter uses strict `<`, so -100 does NOT breach
    container = _fake_container(Decimal("-100"))
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    result = await risk_check(_make_decision("open"), [])
    assert result.action == "open"


@pytest.mark.asyncio
async def test_breach_forces_hold() -> None:
    container = _fake_container(Decimal("-150"))
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    decision = _make_decision("open")
    result = await risk_check(decision, [])
    assert result.action == "hold"


@pytest.mark.asyncio
async def test_hold_always_passes_through() -> None:
    container = _fake_container(Decimal("-9999"))  # way past cap
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    result = await risk_check(_make_decision("hold"), [])
    assert result.action == "hold"  # unchanged, limiter never even called for hold


@pytest.mark.asyncio
async def test_limiter_exception_is_non_fatal() -> None:
    container = MagicMock()
    container.trade_repo.realized_pnl_since = AsyncMock(
        side_effect=RuntimeError("db offline")
    )
    session = MagicMock()
    session.close = AsyncMock()
    container.open_session = AsyncMock(return_value=session)

    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    # Should NOT raise; should pass decision through unchanged
    result = await risk_check(_make_decision("open"), [])
    assert result.action == "open"


@pytest.mark.asyncio
async def test_close_action_also_capped() -> None:
    """The cap applies to close + partial_close too (any non-hold action)."""
    container = _fake_container(Decimal("-200"))
    risk_check = _build_risk_check_fn(container, _fake_settings(100.0))
    result = await risk_check(_make_decision("close"), [])
    assert result.action == "hold"


# ---------------------------------------------------------------------------
# DailyLossLimiter / DailyLossCap direct unit tests
# ---------------------------------------------------------------------------


def test_daily_loss_cap_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError):
        DailyLossCap(cap_usdt=Decimal("0"))
    with pytest.raises(ValueError):
        DailyLossCap(cap_usdt=Decimal("-50"))


@pytest.mark.asyncio
async def test_limiter_check_returns_true_on_breach() -> None:
    session = MagicMock()
    session.close = AsyncMock()

    async def factory() -> MagicMock:
        return session

    repo = MagicMock()
    repo.realized_pnl_since = AsyncMock(return_value=Decimal("-250"))
    limiter = DailyLossLimiter(
        trade_repo=repo,
        session_factory=factory,
        cap=DailyLossCap(cap_usdt=Decimal("100")),
    )
    assert await limiter.check() is True


@pytest.mark.asyncio
async def test_limiter_check_returns_false_on_no_breach() -> None:
    session = MagicMock()
    session.close = AsyncMock()

    async def factory() -> MagicMock:
        return session

    repo = MagicMock()
    repo.realized_pnl_since = AsyncMock(return_value=Decimal("-30"))
    limiter = DailyLossLimiter(
        trade_repo=repo,
        session_factory=factory,
        cap=DailyLossCap(cap_usdt=Decimal("100")),
    )
    assert await limiter.check() is False
