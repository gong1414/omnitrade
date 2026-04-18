"""Persistence repository tests — SQLite in-memory sessions.

Tests entity → ORM → entity round-trips for all 8 repositories.
Confirms apply_three_way_state() emits exactly ONE UPDATE statement
via SQLAlchemy event listener.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omnitrade.domain.entities import (
    AccountSnapshot,
    AgentDecision,
    Position,
    Trade,
    TradeOutcome,
    TradingLesson,
    TradingSignal,
)
from omnitrade.infrastructure.persistence.models import Base
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.config_repository import ConfigRepository
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from omnitrade.infrastructure.persistence.repositories.lesson_repository import LessonRepository
from omnitrade.infrastructure.persistence.repositories.outcome_repository import OutcomeRepository
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.signal_repository import SignalRepository
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository


@pytest.fixture()
async def session() -> AsyncSession:
    """Create an in-memory SQLite async session with schema bootstrapped."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
    await engine.dispose()


_NOW = datetime(2026, 4, 17, 0, 0, 0, tzinfo=UTC)


# ── Position ─────────────────────────────────────────────────────────────


def _make_position(**kwargs) -> Position:
    defaults = dict(
        symbol="BTC_USDT",
        quantity=Decimal("0.1"),
        entry_price=Decimal("63000"),
        current_price=Decimal("64000"),
        liquidation_price=Decimal("58000"),
        unrealized_pnl=Decimal("100"),
        leverage=10,
        side="long",
        entry_order_id="ord-001",
        opened_at=_NOW,
    )
    defaults.update(kwargs)
    return Position(**defaults)


async def test_position_create_get_roundtrip(session: AsyncSession) -> None:
    repo = PositionRepository()
    pos = _make_position()
    created = await repo.create(session, pos)
    assert created.id is not None
    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.symbol == "BTC_USDT"
    assert fetched.entry_price == Decimal("63000")
    assert fetched.leverage == 10


async def test_position_get_by_symbol(session: AsyncSession) -> None:
    repo = PositionRepository()
    pos = _make_position(symbol="ETH_USDT")
    await repo.create(session, pos)
    found = await repo.get_by_symbol(session, "ETH_USDT")
    assert found is not None
    assert found.symbol == "ETH_USDT"


async def test_position_list_all(session: AsyncSession) -> None:
    repo = PositionRepository()
    await repo.create(session, _make_position(symbol="BTC_USDT"))
    all_pos = await repo.list_all(session)
    assert len(all_pos) == 1


async def test_position_delete(session: AsyncSession) -> None:
    repo = PositionRepository()
    pos = await repo.create(session, _make_position())
    await repo.delete(session, pos.id)  # type: ignore[arg-type]
    assert await repo.get(session, pos.id) is None  # type: ignore[arg-type]


async def test_apply_three_way_state_single_update(session: AsyncSession) -> None:
    """apply_three_way_state must emit exactly ONE UPDATE statement.

    We verify this by capturing statements via SQLAlchemy's engine-level
    before_cursor_execute event on the underlying sync connection.
    """
    from sqlalchemy import event as sa_event

    repo = PositionRepository()
    pos = await repo.create(session, _make_position())

    update_statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if statement.strip().upper().startswith("UPDATE"):
            update_statements.append(statement)

    # Get the underlying sync engine from the async session's bind
    sync_engine = session.bind.sync_engine  # type: ignore[union-attr]
    sa_event.listen(sync_engine, "before_cursor_execute", capture)

    try:
        await repo.apply_three_way_state(
            session,
            pos.id,  # type: ignore[arg-type]
            partial_close_pct=Decimal("10"),
            stop_loss=Decimal("62000"),
            peak_pnl=Decimal("5"),
        )
    finally:
        sa_event.remove(sync_engine, "before_cursor_execute", capture)

    # Exactly ONE UPDATE for the three-way state
    assert len(update_statements) == 1, (
        f"Expected 1 UPDATE, got {len(update_statements)}: {update_statements}"
    )

    # Verify values were written
    updated = await repo.get(session, pos.id)  # type: ignore[arg-type]
    assert updated is not None
    assert updated.cumulative_close_pct == Decimal("10")
    assert updated.stop_loss == Decimal("62000")
    assert updated.trailing_peak_pnl_pct == Decimal("5")


async def test_apply_three_way_state_null_stop_loss(session: AsyncSession) -> None:
    repo = PositionRepository()
    pos = await repo.create(session, _make_position(stop_loss=Decimal("61000")))
    await repo.apply_three_way_state(
        session,
        pos.id,  # type: ignore[arg-type]
        partial_close_pct=Decimal("20"),
        stop_loss=None,
        peak_pnl=Decimal("8"),
    )
    updated = await repo.get(session, pos.id)  # type: ignore[arg-type]
    assert updated is not None
    assert updated.stop_loss is None
    assert updated.cumulative_close_pct == Decimal("20")


# ── Trade ─────────────────────────────────────────────────────────────────


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        order_id="trade-001",
        symbol="BTC_USDT",
        side="long",
        type="open",
        price=Decimal("64000"),
        quantity=Decimal("0.1"),
        leverage=10,
        timestamp=_NOW,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


async def test_trade_create_get_roundtrip(session: AsyncSession) -> None:
    repo = TradeRepository()
    trade = await repo.create(session, _make_trade())
    assert trade.id is not None
    fetched = await repo.get(session, trade.id)
    assert fetched is not None
    assert fetched.order_id == "trade-001"
    assert fetched.price == Decimal("64000")


async def test_trade_list_by_symbol(session: AsyncSession) -> None:
    repo = TradeRepository()
    await repo.create(session, _make_trade(symbol="BTC_USDT"))
    await repo.create(session, _make_trade(symbol="ETH_USDT", order_id="trade-002"))
    btc_trades = await repo.list_by_symbol(session, "BTC_USDT")
    assert len(btc_trades) == 1
    assert btc_trades[0].symbol == "BTC_USDT"


# ── AccountHistory ────────────────────────────────────────────────────────


def _make_account_snap(**kwargs) -> AccountSnapshot:
    defaults = dict(
        timestamp=_NOW,
        total_value=Decimal("10000"),
        available_cash=Decimal("8500"),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
        return_percent=Decimal("1.5"),
    )
    defaults.update(kwargs)
    return AccountSnapshot(**defaults)


async def test_account_history_roundtrip(session: AsyncSession) -> None:
    repo = AccountHistoryRepository()
    snap = await repo.create(session, _make_account_snap())
    assert snap.id is not None
    fetched = await repo.get(session, snap.id)
    assert fetched is not None
    assert fetched.total_value == Decimal("10000")


async def test_account_history_list_recent(session: AsyncSession) -> None:
    repo = AccountHistoryRepository()
    await repo.create(session, _make_account_snap())
    await repo.create(session, _make_account_snap(total_value=Decimal("10050")))
    recent = await repo.list_recent(session, limit=10)
    assert len(recent) == 2


# ── Signal ────────────────────────────────────────────────────────────────


def _make_signal(**kwargs) -> TradingSignal:
    defaults = dict(
        symbol="BTC_USDT",
        timestamp=_NOW,
        price=Decimal("64000"),
        ema_20=Decimal("63500"),
        macd=Decimal("150"),
        rsi_7=Decimal("55"),
        rsi_14=Decimal("52"),
        volume=Decimal("1234"),
    )
    defaults.update(kwargs)
    return TradingSignal(**defaults)


async def test_signal_create_roundtrip(session: AsyncSession) -> None:
    repo = SignalRepository()
    sig = await repo.create(session, _make_signal())
    assert sig.id is not None
    fetched = await repo.get(session, sig.id)
    assert fetched is not None
    assert fetched.rsi_14 == Decimal("52")


# ── AgentDecision ─────────────────────────────────────────────────────────


def _make_decision(**kwargs) -> AgentDecision:
    defaults = dict(
        timestamp=_NOW,
        iteration=1,
        market_analysis='{"price": 64000}',
        decision="hold",
        actions_taken="[]",
        account_value=Decimal("10000"),
        positions_count=1,
    )
    defaults.update(kwargs)
    return AgentDecision(**defaults)


async def test_decision_create_roundtrip(session: AsyncSession) -> None:
    repo = DecisionRepository()
    dec = await repo.create(session, _make_decision())
    assert dec.id is not None
    fetched = await repo.get(session, dec.id)
    assert fetched is not None
    assert fetched.iteration == 1


async def test_decision_list_recent(session: AsyncSession) -> None:
    repo = DecisionRepository()
    await repo.create(session, _make_decision(iteration=1))
    await repo.create(session, _make_decision(iteration=2))
    recent = await repo.list_recent(session, limit=5)
    assert len(recent) == 2


# ── TradingLesson ─────────────────────────────────────────────────────────


def _make_lesson(**kwargs) -> TradingLesson:
    defaults = dict(
        pattern="BTC RSI oversold",
        action="open_long",
        outcome="profitable",
        lesson="RSI below 30 with volume spike = good entry",
        created_at=_NOW,
    )
    defaults.update(kwargs)
    return TradingLesson(**defaults)


async def test_lesson_create_roundtrip(session: AsyncSession) -> None:
    repo = LessonRepository()
    lesson = await repo.create(session, _make_lesson())
    assert lesson.id is not None
    fetched = await repo.get(session, lesson.id)
    assert fetched is not None
    assert fetched.pattern == "BTC RSI oversold"


async def test_lesson_list_active_filters_archived(session: AsyncSession) -> None:
    repo = LessonRepository()
    active = await repo.create(session, _make_lesson())
    archived = await repo.create(session, _make_lesson(pattern="archived_one"))
    await repo.archive(session, archived.id)  # type: ignore[arg-type]
    active_list = await repo.list_active(session)
    assert len(active_list) == 1
    assert active_list[0].id == active.id


# ── TradeOutcome ──────────────────────────────────────────────────────────


def _make_outcome(**kwargs) -> TradeOutcome:
    defaults = dict(
        symbol="BTC_USDT",
        side="long",
        created_at=_NOW,
    )
    defaults.update(kwargs)
    return TradeOutcome(**defaults)


async def test_outcome_create_roundtrip(session: AsyncSession) -> None:
    repo = OutcomeRepository()
    outcome = await repo.create(session, _make_outcome())
    assert outcome.id is not None
    fetched = await repo.get(session, outcome.id)
    assert fetched is not None
    assert fetched.symbol == "BTC_USDT"


async def test_outcome_mark_extracted(session: AsyncSession) -> None:
    repo = OutcomeRepository()
    outcome = await repo.create(session, _make_outcome())
    unextracted = await repo.list_unextracted(session)
    assert len(unextracted) == 1
    await repo.mark_extracted(session, outcome.id)  # type: ignore[arg-type]
    unextracted_after = await repo.list_unextracted(session)
    assert len(unextracted_after) == 0


# ── SystemConfig ──────────────────────────────────────────────────────────


async def test_config_set_get_roundtrip(session: AsyncSession) -> None:
    repo = ConfigRepository()
    cfg = await repo.set(session, "trading_strategy", "arena-steward")
    assert cfg.key == "trading_strategy"
    assert cfg.value == "arena-steward"
    fetched = await repo.get(session, "trading_strategy")
    assert fetched is not None
    assert fetched.value == "arena-steward"


async def test_config_upsert(session: AsyncSession) -> None:
    repo = ConfigRepository()
    await repo.set(session, "max_leverage", "10")
    updated = await repo.set(session, "max_leverage", "20")
    assert updated.value == "20"
    all_cfg = await repo.list_all(session)
    assert len(all_cfg) == 1


async def test_config_delete(session: AsyncSession) -> None:
    repo = ConfigRepository()
    await repo.set(session, "temp_key", "val")
    await repo.delete(session, "temp_key")
    assert await repo.get(session, "temp_key") is None
