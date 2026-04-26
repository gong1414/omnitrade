"""Tests for the G5 QA-phrase guardrail (T3).

Covers:

1. Every phrase listed in ``CLAUDE.md`` Gate G5 triggers exactly one
   ``EVENT_ORCHESTRATOR_ERROR`` publish (parameterised).
2. Clean reasoning text never publishes.
3. Reasoning that contains *several* fault phrases publishes only once
   (dedup contract — first hit wins).
4. The factory ``build_agno_think_fn`` wires ``post_hooks=[...]`` into
   the Agno ``Agent`` kwargs whenever an ``event_bus`` is supplied.

The post_hook itself is async — Agno's ``aexecute_post_hooks`` awaits
coroutine hooks directly, so we drive the hook with ``pytest.mark.asyncio``
and a fake event-bus that records every ``publish`` call into a list.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from omnitrade.agents.guardrails.qa_phrase import (
    build_qa_phrase_post_hook,
    scan_for_qa_phrase,
)
from omnitrade.application.events.bus import EVENT_ORCHESTRATOR_ERROR

# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class _FakeEventBus:
    """Records every (event_name, payload) tuple sent to ``publish``."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        self.published.append((event_name, payload))


def _run_output(content: str) -> SimpleNamespace:
    """Stand-in for ``agno.run.agent.RunOutput`` — duck-typed on ``.content``."""
    return SimpleNamespace(content=content)


# --------------------------------------------------------------------------- #
# 1. Every G5 phrase fires                                                    #
# --------------------------------------------------------------------------- #

# Each entry is (text_seen_by_hook, expected_matched_phrase).
# Order tracks CLAUDE.md "Gate G5" verbatim; substring patterns at the end.
_G5_PHRASES: tuple[tuple[str, str], ...] = (
    # Chinese literal phrases
    ("风险检查触发了异常情况", "异常"),
    ("订单回报里有错误", "错误"),
    ("仓位与账面不符合", "不符合"),
    ("行情更新明显不正常", "不正常"),
    ("CCXT 报告数据同步故障 — 重试中", "数据同步故障"),
    ("系统异常已被记录", "系统异常"),
    ("出现数据异常,需要复核", "数据异常"),
    # English literal phrases (case-insensitive)
    ("detected a price anomaly in the feed", "anomaly"),
    ("ERROR: orderbook fetch failed", "error"),
    ("positions vs ledger are inconsistent", "inconsistent"),
    ("malformed JSON returned by upstream", "malformed"),
    ("data sync issue between exchange and DB", "data sync issue"),
    ("encountered a system issue mid-cycle", "system issue"),
    ("phantom positions seen again", "phantom"),
    # Compound substring patterns
    ("所有持仓都是 0,看起来不对", "所有 X 都是 0"),
    ("All balances are 0 right now", "all X are 0/null/empty"),
    ("all account fields are null", "all X are 0/null/empty"),
    ("All positions are empty after sync", "all X are 0/null/empty"),
)


@pytest.mark.parametrize(
    ("text", "expected_phrase"),
    _G5_PHRASES,
    ids=[expected for _, expected in _G5_PHRASES],
)
@pytest.mark.asyncio
async def test_every_g5_phrase_publishes_orchestrator_error(
    text: str,
    expected_phrase: str,
) -> None:
    bus = _FakeEventBus()
    hook = build_qa_phrase_post_hook(bus)

    await hook(run_output=_run_output(text))

    assert len(bus.published) == 1, (
        f"expected exactly one publish for text {text!r}; got {bus.published!r}"
    )
    event_name, payload = bus.published[0]
    assert event_name == EVENT_ORCHESTRATOR_ERROR
    assert payload["reason"] == "qa_phrase_match"
    assert payload["phrase"] == expected_phrase
    # Snippet is non-empty and includes the matched substring (or the
    # compound-pattern's anchor word for substring patterns).
    assert isinstance(payload["snippet"], str)
    assert payload["snippet"]


# --------------------------------------------------------------------------- #
# 2. Clean text is silent                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clean_text_does_not_publish() -> None:
    bus = _FakeEventBus()
    hook = build_qa_phrase_post_hook(bus)

    clean_samples = [
        "opened a long on BTC at $80k",
        "holding existing positions; momentum intact",
        "partial close 30% on ETH per take-profit ladder",
        "",  # empty content — must be safe.
    ]
    for text in clean_samples:
        await hook(run_output=_run_output(text))

    assert bus.published == [], f"clean text should never publish; got {bus.published!r}"


@pytest.mark.asyncio
async def test_missing_run_output_is_silent() -> None:
    """Defensive: if Agno calls the hook without ``run_output`` (or with
    a non-string content) we must NOT crash — the cycle keeps going."""
    bus = _FakeEventBus()
    hook = build_qa_phrase_post_hook(bus)

    await hook()  # no kwargs at all
    await hook(run_output=None)
    await hook(run_output=SimpleNamespace(content=None))
    await hook(run_output=SimpleNamespace())  # no .content attribute

    assert bus.published == []


# --------------------------------------------------------------------------- #
# 3. Multiple phrases in one output → exactly one publish                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_multiple_phrases_dedup_to_single_publish() -> None:
    bus = _FakeEventBus()
    hook = build_qa_phrase_post_hook(bus)

    # Three different fault phrases in one block of reasoning. The hook
    # must publish ONE event (the earliest hit) — the dashboard banner
    # should never stutter on a single cycle.
    text = "数据异常: phantom positions detected and the feed is inconsistent — all balances are 0"
    await hook(run_output=_run_output(text))

    assert len(bus.published) == 1
    event_name, payload = bus.published[0]
    assert event_name == EVENT_ORCHESTRATOR_ERROR
    # "数据异常" appears at index 0 — earliest match wins.
    assert payload["phrase"] == "数据异常"


# --------------------------------------------------------------------------- #
# scan_for_qa_phrase — the pure-function half of the API                      #
# --------------------------------------------------------------------------- #


def test_scan_returns_none_for_clean_text() -> None:
    assert scan_for_qa_phrase("opened a long on BTC at $80k") is None
    assert scan_for_qa_phrase("") is None


def test_scan_snippet_includes_match_with_context() -> None:
    text = "preface text " * 10 + "数据同步故障" + " trailing text" * 10
    result = scan_for_qa_phrase(text)
    assert result is not None
    phrase, snippet = result
    assert phrase == "数据同步故障"
    assert "数据同步故障" in snippet
    # Window is ±60 chars; snippet should be much shorter than the input
    # but include some surrounding context.
    assert len(snippet) < len(text)
    assert len(snippet) > len("数据同步故障")


# --------------------------------------------------------------------------- #
# 4. Wired into Agent via build_agno_think_fn                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_build_agno_think_fn_wires_post_hooks_when_event_bus_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``event_bus`` is passed, the Agno ``Agent`` constructor
    receives a ``post_hooks`` kwarg containing exactly one async callable
    (the QA-phrase hook). When ``event_bus`` is omitted, no post_hooks
    are wired so legacy callers keep their bit-for-bit behaviour.
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    from agno.agent import Agent
    from pydantic import SecretStr

    from omnitrade.agents import trading_agent
    from omnitrade.config import Settings
    from omnitrade.domain.entities import MarketSnapshot
    from omnitrade.domain.enums import StrategyName

    captured_kwargs: dict[str, Any] = {}

    class _StubAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

        async def arun(self, *_args: Any, **_kwargs: Any) -> Any:
            return SimpleNamespace(content="hold for now")

    # Patch only the symbol the module imported; leaves the real Agent
    # class intact for other tests.
    monkeypatch.setattr(trading_agent, "Agent", _StubAgent)

    # Stub MCP bridge so we don't spawn subprocesses.
    async def _noop_connect(self: Any) -> None:
        return None

    monkeypatch.setattr(trading_agent.AgnoMCPBridge, "connect", _noop_connect, raising=False)

    settings = Settings(
        llm_api_key=SecretStr("test-key"),
        trading_strategy=StrategyName.AI_AUTONOMOUS.value,
    )

    def render_messages(**_kwargs: Any) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ]

    async def market_block(_container: Any, _market: MarketSnapshot) -> str:
        return ""

    async def trades_block(_container: Any) -> str:
        return ""

    bus = _FakeEventBus()

    fn = trading_agent.build_agno_think_fn(
        container=SimpleNamespace(),
        settings=settings,
        render_messages=render_messages,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=market_block,
        recent_trades_block_builder=trades_block,
        event_bus=bus,  # type: ignore[arg-type]
    )

    market = MarketSnapshot(
        timestamp=datetime.now(UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("50000")},
        positions=[],
    )
    await fn(market, [])

    # Sanity: stub Agent ran and we captured kwargs.
    assert captured_kwargs, "expected the patched Agent constructor to fire"
    post_hooks = captured_kwargs.get("post_hooks")
    assert isinstance(post_hooks, list) and len(post_hooks) == 1
    assert post_hooks[0].__name__ == "qa_phrase_post_hook"

    # And the Agent class we patched was Agno's real export — protect
    # against the import drifting under us.
    assert Agent is not _StubAgent

    # ── second pass without event_bus → no post_hooks wired ────────── #
    captured_kwargs.clear()
    fn2 = trading_agent.build_agno_think_fn(
        container=SimpleNamespace(),
        settings=settings,
        render_messages=render_messages,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=market_block,
        recent_trades_block_builder=trades_block,
    )
    await fn2(market, [])
    assert "post_hooks" not in captured_kwargs
