"""DecisionRepository — structured fields round-trip tests (PR-B1 Step 5).

Covers:
- Legacy Decision (6 new fields all None) → DB new 6 cols all NULL → read back None
- Structured Decision (6 new fields populated) → DB cols filled + JSON serialised
- gates_passed round-trip: list[str] → JSON string → list[str]
- plan round-trip: dict → JSON string → dict
- output_language round-trip: "zh" / "en" / None
- structured_confidence: float → DB column ``confidence`` → domain structured_confidence
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from omnitrade.domain.entities import AgentDecision
from omnitrade.infrastructure.persistence.models import Base
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)

_NOW = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
async def session() -> AsyncSession:
    """In-memory SQLite async session with full schema (including 0003 columns)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _make_legacy_decision(**kwargs) -> AgentDecision:
    """AgentDecision with the 6 new fields all None (legacy path)."""
    defaults = dict(
        timestamp=_NOW,
        iteration=1,
        market_analysis='{"symbols": ["BTC_USDT"]}',
        decision="hold",
        actions_taken="[]",
        account_value=Decimal("1000.00"),
        positions_count=0,
    )
    defaults.update(kwargs)
    return AgentDecision(**defaults)


def _make_structured_decision(**kwargs) -> AgentDecision:
    """AgentDecision with all 6 structured fields populated."""
    defaults = dict(
        timestamp=_NOW,
        iteration=2,
        market_analysis='{"symbols": ["BTC_USDT"]}',
        decision="open",
        actions_taken='[{"action": "open_position"}]',
        account_value=Decimal("1050.00"),
        positions_count=1,
        market_context="BTC is in a sustained uptrend with EMA20 > EMA50.",
        gates_passed=["EMA alignment gate: EMA20 > EMA50 confirms uptrend", "RSI gate: RSI > 55"],
        invalidation_condition="Daily close below 42000 USDT invalidates bullish bias.",
        plan={"entry": 43000.0, "stop_loss": 41000.0, "take_profit_1": 46000.0},
        structured_confidence=0.75,
        output_language="zh",
    )
    defaults.update(kwargs)
    return AgentDecision(**defaults)


# ── Legacy path ───────────────────────────────────────────────────────────────


async def test_legacy_decision_new_fields_all_none(session: AsyncSession) -> None:
    """Legacy row: 6 new fields all None → DB NULLs → read back as None."""
    repo = DecisionRepository()
    dec = _make_legacy_decision()

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.market_context is None
    assert fetched.gates_passed is None
    assert fetched.invalidation_condition is None
    assert fetched.plan is None
    assert fetched.structured_confidence is None
    assert fetched.output_language is None


# ── Structured path ───────────────────────────────────────────────────────────


async def test_structured_decision_all_fields_round_trip(session: AsyncSession) -> None:
    """Structured row: all 6 fields populated → written to DB → read back intact."""
    repo = DecisionRepository()
    dec = _make_structured_decision()

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.market_context == dec.market_context
    assert fetched.gates_passed == dec.gates_passed
    assert fetched.invalidation_condition == dec.invalidation_condition
    assert fetched.plan == dec.plan
    assert fetched.structured_confidence == pytest.approx(dec.structured_confidence)
    assert fetched.output_language == dec.output_language


# ── gates_passed round-trip ───────────────────────────────────────────────────


async def test_gates_passed_list_roundtrip(session: AsyncSession) -> None:
    """gates_passed: list[str] is serialised to JSON and deserialised back."""
    repo = DecisionRepository()
    gates = ["gate alpha: evidence A", "gate beta: evidence B", "gate gamma: evidence C"]
    dec = _make_structured_decision(gates_passed=gates)

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert isinstance(fetched.gates_passed, list)
    assert fetched.gates_passed == gates


async def test_gates_passed_empty_list_roundtrip(session: AsyncSession) -> None:
    """Empty gates_passed list round-trips correctly (valid for hold decisions)."""
    repo = DecisionRepository()
    dec = _make_structured_decision(gates_passed=[])

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.gates_passed == []


# ── plan round-trip ───────────────────────────────────────────────────────────


async def test_plan_dict_roundtrip(session: AsyncSession) -> None:
    """plan: dict is serialised to JSON and deserialised back."""
    repo = DecisionRepository()
    plan = {
        "entry": 43000.0,
        "stop_loss": 41000.0,
        "take_profit_1": 46000.0,
        "take_profit_2": 50000.0,
        "risk_usd": 200.0,
        "r_multiple_target": 1.5,
    }
    dec = _make_structured_decision(plan=plan)

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert isinstance(fetched.plan, dict)
    assert fetched.plan == plan


async def test_plan_none_roundtrip(session: AsyncSession) -> None:
    """plan=None (hold decision) round-trips as None."""
    repo = DecisionRepository()
    dec = _make_structured_decision(plan=None)

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.plan is None


# ── output_language round-trip ────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["zh", "en", None])
async def test_output_language_roundtrip(lang: str | None, session: AsyncSession) -> None:
    """output_language 'zh', 'en', and None all survive the DB round-trip."""
    repo = DecisionRepository()
    dec = _make_structured_decision(output_language=lang)

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    assert fetched.output_language == lang


# ── structured_confidence mapping ─────────────────────────────────────────────


@pytest.mark.parametrize("conf", [0.0, 0.5, 0.75, 1.0, None])
async def test_structured_confidence_roundtrip(
    conf: float | None, session: AsyncSession
) -> None:
    """structured_confidence maps to DB column ``confidence`` and back."""
    repo = DecisionRepository()
    dec = _make_structured_decision(structured_confidence=conf)

    created = await repo.create(session, dec)
    await session.commit()

    fetched = await repo.get(session, created.id)
    assert fetched is not None
    if conf is None:
        assert fetched.structured_confidence is None
    else:
        assert fetched.structured_confidence == pytest.approx(conf)


# ── list_recent includes structured fields ────────────────────────────────────


async def test_list_recent_returns_structured_fields(session: AsyncSession) -> None:
    """list_recent correctly deserialises structured fields for all rows."""
    repo = DecisionRepository()
    legacy = _make_legacy_decision(iteration=1)
    structured = _make_structured_decision(iteration=2)

    await repo.create(session, legacy)
    await repo.create(session, structured)
    await session.commit()

    rows = await repo.list_recent(session, limit=10)
    assert len(rows) == 2

    # Most-recent first (iteration 2 = structured)
    structured_row = next(r for r in rows if r.iteration == 2)
    legacy_row = next(r for r in rows if r.iteration == 1)

    # Structured row has fields populated
    assert structured_row.market_context == structured.market_context
    assert structured_row.gates_passed == structured.gates_passed
    assert structured_row.plan == structured.plan
    assert structured_row.structured_confidence == pytest.approx(structured.structured_confidence)

    # Legacy row has all new fields as None
    assert legacy_row.market_context is None
    assert legacy_row.gates_passed is None
    assert legacy_row.plan is None
    assert legacy_row.structured_confidence is None
