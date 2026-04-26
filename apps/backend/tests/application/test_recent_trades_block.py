"""PR-D Phase D3 — _render_recent_trades_block() tests.

Walks 3 corners:
  - empty DB → explicit "no prior decisions yet"
  - 5 decisions → 5 lines, newest first, contain age / confidence / brief
  - 20 decisions → limit honoured (only 5 rendered)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from omnitrade.application.composition import _render_recent_trades_block
from omnitrade.domain.entities import AgentDecision


def _make_decision(
    *,
    id_: int,
    iteration: int,
    action: str = "hold",
    ts_minutes_ago: int = 0,
    confidence: float | None = 0.65,
    market_context: str | None = "BTC range-bound around 75k; weak signal.",
) -> AgentDecision:
    ts = datetime.now(UTC) - timedelta(minutes=ts_minutes_ago)
    return AgentDecision(
        id=id_,
        timestamp=ts,
        iteration=iteration,
        decision=action,
        market_analysis="{}",
        actions_taken="[]",
        account_value=Decimal("1000"),
        positions_count=0,
        run_id="",
        market_context=market_context,
        gates_passed=[],
        invalidation_condition="",
        plan=None,
        structured_confidence=confidence,
        output_language="zh",
    )


def _fake_container(recent: list[AgentDecision]) -> MagicMock:
    container = MagicMock()
    container.decision_repo.list_recent_for_feedback = AsyncMock(return_value=recent)
    # open_session() returns a session that supports close()
    session = MagicMock()
    session.close = AsyncMock()
    container.open_session = AsyncMock(return_value=session)
    return container


@pytest.mark.asyncio
async def test_block_empty_db_returns_explicit_message() -> None:
    container = _fake_container([])
    block = await _render_recent_trades_block(container)
    assert "no prior decisions yet" in block


@pytest.mark.asyncio
async def test_block_with_5_decisions_renders_5_lines() -> None:
    decisions = [
        _make_decision(id_=5, iteration=23, action="open", ts_minutes_ago=2),
        _make_decision(id_=4, iteration=22, action="hold", ts_minutes_ago=4),
        _make_decision(id_=3, iteration=21, action="close", ts_minutes_ago=6, confidence=0.82),
        _make_decision(id_=2, iteration=20, action="hold", ts_minutes_ago=8, confidence=None),
        _make_decision(id_=1, iteration=19, action="partial_close", ts_minutes_ago=10),
    ]
    container = _fake_container(decisions)
    block = await _render_recent_trades_block(container)
    lines = block.splitlines()
    # 1 header + 5 entries
    assert len(lines) == 6
    assert lines[0].startswith("Recent cycles")
    assert "Cycle #23" in lines[1]
    assert "open" in lines[1]
    assert "Cycle #19" in lines[5]
    # Age rendering — min ago
    assert "2 min ago" in lines[1]
    # Confidence rendering — float formatted, None rendered as "—"
    assert "confidence=0.65" in lines[1]
    assert "confidence=—" in lines[4]  # id_=2 had None


@pytest.mark.asyncio
async def test_block_respects_limit_parameter_passthrough() -> None:
    # Limit enforcement lives in DecisionRepository, but the renderer must
    # pass limit=5 into list_recent_for_feedback exactly.
    decisions = [
        _make_decision(id_=i, iteration=i, ts_minutes_ago=i) for i in range(5, 0, -1)
    ]
    container = _fake_container(decisions)
    await _render_recent_trades_block(container)
    container.decision_repo.list_recent_for_feedback.assert_awaited_once()
    call_kwargs = container.decision_repo.list_recent_for_feedback.await_args.kwargs
    assert call_kwargs.get("limit") == 5


@pytest.mark.asyncio
async def test_block_truncates_long_market_context() -> None:
    long_context = "X" * 500
    decisions = [
        _make_decision(id_=1, iteration=1, market_context=long_context, ts_minutes_ago=1),
    ]
    container = _fake_container(decisions)
    block = await _render_recent_trades_block(container)
    # 160-char cap + "..." suffix
    assert "..." in block
    # Should NOT dump the full 500-char string
    assert "X" * 200 not in block


@pytest.mark.asyncio
async def test_block_graceful_degradation_on_db_failure() -> None:
    container = MagicMock()
    container.open_session = AsyncMock(side_effect=RuntimeError("db gone"))
    block = await _render_recent_trades_block(container)
    assert "feedback unavailable" in block
