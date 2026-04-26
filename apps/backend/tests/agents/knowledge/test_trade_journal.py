"""Tests for the T10 trade-journal RAG layer.

Acceptance criteria:
  1. ``build_trade_journal_knowledge`` returns ``None`` (with an info-log)
     when ``settings.agno_postgres_url`` is unset — match T4's skip pattern.
  2. ``build_trade_journal_knowledge`` returns a Knowledge instance when
     URL + embedder/LLM API key are wired (Postgres connection mocked —
     no live DB required for unit tests).
  3. The embedder-key skip path emits a warning log and returns None
     without crashing.
  4. ``serialise_decision_for_journal`` produces non-empty content and the
     expected metadata keys.
  5. ``record_decision_to_knowledge`` calls ``add_content_async`` once and
     swallows any inner exception.
  6. The integration smoke (``requires_postgres``) inserts + searches and
     is skipped cleanly without a live Postgres.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnitrade.agents.knowledge import (
    build_trade_journal_knowledge,
    record_decision_to_knowledge,
    serialise_decision_for_journal,
)
from omnitrade.config import Settings


def _fresh_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "agno_postgres_url": None,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ── Acceptance 1: no-op when Postgres URL is unset ──────────────────────── #


def test_build_returns_none_when_postgres_url_unset(capsys: Any) -> None:
    settings = _fresh_settings(agno_postgres_url=None)

    out = build_trade_journal_knowledge(settings)
    captured = capsys.readouterr()

    assert out is None
    # structlog (the project's logger) writes JSON-ish lines to stdout
    # rather than stdlib logging. Match the keys we emitted.
    combined = captured.out + captured.err
    assert "trade_journal.build.skip" in combined
    assert "agno_postgres_url" in combined


# ── Acceptance 2: returns Knowledge instance when wired ─────────────────── #


def test_build_returns_knowledge_when_url_set_with_fastembed() -> None:
    """Default provider (fastembed) needs no API key."""
    settings = _fresh_settings(
        agno_postgres_url="postgresql+psycopg://u:p@h:5432/d",
    )
    assert settings.embedder_provider == "fastembed"

    fake_pgvector_instance = MagicMock(name="PgVectorInstance")
    fake_pgvector_cls = MagicMock(name="PgVectorCls", return_value=fake_pgvector_instance)
    fake_knowledge_instance = MagicMock(name="KnowledgeInstance")
    fake_knowledge_cls = MagicMock(name="KnowledgeCls", return_value=fake_knowledge_instance)
    fake_embedder_instance = MagicMock(name="FastEmbedInstance")
    fake_embedder_cls = MagicMock(name="FastEmbedCls", return_value=fake_embedder_instance)

    with (
        patch("agno.vectordb.pgvector.PgVector", fake_pgvector_cls),
        patch("agno.knowledge.knowledge.Knowledge", fake_knowledge_cls),
        patch("agno.knowledge.embedder.fastembed.FastEmbedEmbedder", fake_embedder_cls),
    ):
        out = build_trade_journal_knowledge(settings)

    assert out is fake_knowledge_instance
    fake_embedder_cls.assert_called_once()
    assert fake_embedder_cls.call_args.kwargs["id"] == settings.embedder_model_id
    fake_pgvector_cls.assert_called_once()
    pg_kwargs = fake_pgvector_cls.call_args.kwargs
    assert pg_kwargs["table_name"] == "trade_journal"
    assert pg_kwargs["embedder"] is fake_embedder_instance


def test_build_returns_knowledge_with_openai_provider() -> None:
    """Operator-overridden ``openai`` provider routes via OpenAIEmbedder."""
    settings = _fresh_settings(
        agno_postgres_url="postgresql+psycopg://u:p@h:5432/d",
        embedder_provider="openai",
        llm_api_key="sk-fake",  # type: ignore[arg-type]
        embedder_model_id="text-embedding-3-small",
    )

    fake_pgvector_cls = MagicMock(name="PgVectorCls", return_value=MagicMock())
    fake_knowledge_cls = MagicMock(name="KnowledgeCls", return_value=MagicMock())
    fake_embedder_instance = MagicMock(name="OpenAIEmbedderInstance")
    fake_embedder_cls = MagicMock(name="OpenAIEmbedderCls", return_value=fake_embedder_instance)

    with (
        patch("agno.vectordb.pgvector.PgVector", fake_pgvector_cls),
        patch("agno.knowledge.knowledge.Knowledge", fake_knowledge_cls),
        patch("agno.knowledge.embedder.openai.OpenAIEmbedder", fake_embedder_cls),
    ):
        out = build_trade_journal_knowledge(settings)

    assert out is not None
    fake_embedder_cls.assert_called_once()
    em_kwargs = fake_embedder_cls.call_args.kwargs
    assert em_kwargs["api_key"] == "sk-fake"
    assert em_kwargs["id"] == "text-embedding-3-small"


# ── Acceptance 3: embedder key missing → warn + None (openai provider) ──── #


def test_build_returns_none_when_embedder_key_missing(capsys: Any) -> None:
    settings = _fresh_settings(
        agno_postgres_url="postgresql+psycopg://u:p@h:5432/d",
        embedder_provider="openai",
        # Both embedder_api_key and llm_api_key intentionally unset.
    )

    out = build_trade_journal_knowledge(settings)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert out is None
    assert "trade_journal.build.skip" in combined
    assert "embedder_api_key" in combined or "llm_api_key" in combined


def test_build_handles_import_error_gracefully() -> None:
    """Missing pgvector / fastembed extras should log + return None, not raise."""
    settings = _fresh_settings(
        agno_postgres_url="postgresql+psycopg://u:p@h:5432/d",
    )

    import builtins

    real_import = builtins.__import__
    blocked = {
        "agno.vectordb.pgvector",
        "agno.knowledge.knowledge",
        "agno.knowledge.embedder.fastembed",
    }

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in blocked:
            raise ImportError(f"simulated missing dep: {name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        out = build_trade_journal_knowledge(settings)

    assert out is None


# ── Acceptance 4: serialiser shape ──────────────────────────────────────── #


class _FakeStructured:
    """Minimal stand-in shaped like both Decision and StructuredReason."""

    def __init__(self, **fields: Any) -> None:
        for k, v in fields.items():
            setattr(self, k, v)


def test_serialise_produces_content_and_metadata() -> None:
    sr = _FakeStructured(
        market_context="BTC trending up on EMA20>EMA50; RSI 62.",
        gates_passed=[
            "EMA alignment gate: EMA20 > EMA50 > EMA200 confirms uptrend",
            "Volume gate: 15m volume 1.4x rolling average",
        ],
        invalidation_condition="Daily close below 60000 USDT.",
        plan={"entry": 67000, "stop_loss": 65500, "take_profit_1": 70000},
        confidence=0.72,
        justification="Trend + momentum align; risk-reward 1:2.",
        action="open",
    )
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

    content, metadata = serialise_decision_for_journal(
        sr,
        run_id="cycle-42",
        timestamp=ts,
    )

    assert content
    assert "BTC trending up" in content
    assert "EMA alignment gate" in content
    assert "Daily close below 60000" in content
    assert "open" in content.lower()
    # Metadata shape: must include filterable keys for downstream queries.
    assert metadata["run_id"] == "cycle-42"
    assert metadata["timestamp"] == ts.isoformat()
    assert metadata["action"] == "open"
    assert metadata["confidence"] == pytest.approx(0.72)


def test_serialise_handles_hold_with_null_plan() -> None:
    """Hold decisions carry plan=None and should still serialise cleanly."""
    sr = _FakeStructured(
        market_context="Range-bound; no clean directional bias.",
        gates_passed=[],
        invalidation_condition="Break above resistance with volume.",
        plan=None,
        confidence=0.35,
        justification="No setup qualifies; staying flat.",
        action="hold",
    )
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

    content, metadata = serialise_decision_for_journal(
        sr,
        run_id="cycle-7",
        timestamp=ts,
    )

    assert "Range-bound" in content
    # No plan section emitted when plan is None.
    assert "Plan:" not in content
    assert metadata["action"] == "hold"
    assert metadata["confidence"] == pytest.approx(0.35)


def test_serialise_truncates_oversize_content() -> None:
    """Justifications can run long; content must stay bounded."""
    huge = "X" * 20_000
    sr = _FakeStructured(
        market_context="ctx",
        gates_passed=[],
        invalidation_condition="inv",
        plan=None,
        confidence=0.5,
        justification=huge,
        action="hold",
    )
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

    content, _meta = serialise_decision_for_journal(
        sr,
        run_id="r1",
        timestamp=ts,
    )

    assert len(content) <= 4_000
    assert "[...truncated]" in content


# ── Acceptance 5: record helper calls add_content_async + swallows errors ── #


@pytest.mark.asyncio
async def test_record_calls_add_content_async() -> None:
    sr = _FakeStructured(
        market_context="ctx",
        gates_passed=["g"],
        invalidation_condition="inv",
        plan=None,
        confidence=0.5,
        justification="j",
        action="hold",
    )
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    knowledge = MagicMock()
    knowledge.add_content_async = AsyncMock()

    await record_decision_to_knowledge(
        knowledge,
        sr,
        run_id="cycle-1",
        timestamp=ts,
    )

    knowledge.add_content_async.assert_awaited_once()
    call = knowledge.add_content_async.await_args
    assert call.kwargs["name"] == "cycle-cycle-1"
    assert "ctx" in call.kwargs["text_content"]
    assert call.kwargs["metadata"]["run_id"] == "cycle-1"


@pytest.mark.asyncio
async def test_record_short_circuits_on_none_knowledge() -> None:
    """None handle = no-op (Postgres unwired path)."""
    sr = _FakeStructured(market_context="ctx", action="hold")
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    # Should not raise.
    await record_decision_to_knowledge(None, sr, run_id="r", timestamp=ts)


@pytest.mark.asyncio
async def test_record_swallows_inner_exceptions(capsys: Any) -> None:
    sr = _FakeStructured(
        market_context="ctx",
        gates_passed=[],
        invalidation_condition="inv",
        plan=None,
        confidence=0.5,
        justification="j",
        action="hold",
    )
    ts = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    knowledge = MagicMock()
    knowledge.add_content_async = AsyncMock(side_effect=RuntimeError("boom"))

    # Should not raise — record_decision_to_knowledge log+swallows.
    await record_decision_to_knowledge(
        knowledge,
        sr,
        run_id="cycle-1",
        timestamp=ts,
    )

    knowledge.add_content_async.assert_awaited_once()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "trade_journal.record.failed" in combined
    assert "boom" in combined


# ── Acceptance 6: integration smoke — gated on AGNO_POSTGRES_URL ────────── #


@pytest.mark.requires_postgres
@pytest.mark.skipif(
    not os.getenv("AGNO_POSTGRES_URL"),
    reason="requires_postgres: needs a live Postgres URL with pgvector via AGNO_POSTGRES_URL",
)
@pytest.mark.asyncio
async def test_record_then_search_round_trips_against_live_postgres() -> None:
    """Insert 3 fake decisions + assert ``knowledge.search`` returns a relevant hit.

    Skipped without live Postgres + pgvector. The factory itself returns
    ``None`` when the env is missing; this test exercises the full
    ingest + retrieve loop when the operator has a Postgres + pgvector
    image running locally.
    """
    settings = _fresh_settings(
        agno_postgres_url=os.environ["AGNO_POSTGRES_URL"],
    )
    knowledge = build_trade_journal_knowledge(settings)
    assert knowledge is not None, "factory should produce a Knowledge handle"

    ts = datetime.now(tz=UTC)
    decisions = [
        _FakeStructured(
            market_context="BTC strongly bullish on EMA20>EMA50; RSI 65.",
            gates_passed=["EMA alignment", "RSI > 50"],
            invalidation_condition="Daily close below 60k.",
            plan={"entry": 67000, "stop_loss": 65500},
            confidence=0.78,
            justification="Trend + momentum align.",
            action="open",
        ),
        _FakeStructured(
            market_context="ETH range-bound; no clean signal.",
            gates_passed=[],
            invalidation_condition="Break of range.",
            plan=None,
            confidence=0.35,
            justification="No qualifying setup.",
            action="hold",
        ),
        _FakeStructured(
            market_context="BTC trending strongly higher with volume confirmation.",
            gates_passed=["EMA stack", "Volume 1.5x"],
            invalidation_condition="Lower-low daily close.",
            plan={"entry": 68000, "stop_loss": 66000},
            confidence=0.81,
            justification="Strong trend continuation.",
            action="open",
        ),
    ]
    for i, d in enumerate(decisions):
        await record_decision_to_knowledge(
            knowledge,
            d,
            run_id=f"smoke-{i}",
            timestamp=ts,
        )

    results = await knowledge.asearch(
        "BTC bullish trend with EMA alignment",
        max_results=2,
    )
    assert len(results) >= 1
    # Top hit should mention BTC + EMA per our seeded docs.
    top = results[0]
    body = getattr(top, "content", None) or getattr(top, "text", None) or str(top)
    assert "BTC" in body or "EMA" in body
