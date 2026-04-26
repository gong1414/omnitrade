"""Team-advisory wiring contract tests for ``build_agno_think_fn``.

These verify the small surface that
``omnitrade.agents.trading_agent.build_agno_think_fn`` adds when
``settings.multi_agent_enabled`` is true:

  1. Team is built/called only for the two team-eligible strategies
     (``AGGRESSIVE_TEAM`` / ``MULTI_AGENT_CONSENSUS``).
  2. The advisory text is *prepended* to the user prompt seen by the
     main Agent — the team never replaces the Decision contract.
  3. Team failures (build / runtime) soft-degrade: the main Agent still
     runs, the cycle still produces a Decision.

No live LLM calls. Agno ``Agent`` and ``Team`` are replaced with stubs;
the MCP bridge is short-circuited so no subprocesses are spawned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from omnitrade.agents import trading_agent as ta_mod
from omnitrade.config import Settings
from omnitrade.domain.entities import MarketSnapshot
from omnitrade.domain.enums import StrategyName


# ---------------------------------------------------------------------------
# Test fixtures: stub model + agent + bridge so no network call is issued.
# ---------------------------------------------------------------------------


class _StubAgent:
    """Captures construction kwargs + the ``arun`` user prompt."""

    last_kwargs: dict[str, Any] = {}
    last_prompt: str = ""

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs

    async def arun(self, prompt: str) -> SimpleNamespace:
        type(self).last_prompt = prompt
        return SimpleNamespace(content="")


@pytest.fixture
def stub_agno(monkeypatch: pytest.MonkeyPatch) -> type[_StubAgent]:
    """Patch model resolution + Agent class + MCP bridge connect."""
    monkeypatch.setattr(ta_mod, "_resolve_deepseek", lambda settings: object())
    monkeypatch.setattr(ta_mod, "Agent", _StubAgent)

    async def _no_connect(self: Any) -> None:
        return None

    monkeypatch.setattr(ta_mod.AgnoMCPBridge, "connect", _no_connect)
    # Reset captured state so tests in the same module don't leak.
    _StubAgent.last_kwargs = {}
    _StubAgent.last_prompt = ""
    return _StubAgent


def _make_settings(*, multi_agent_enabled: bool, strategy: StrategyName) -> Settings:
    return Settings(
        llm_api_key=SecretStr("test-key"),
        trading_strategy=strategy.value,
        multi_agent_enabled=multi_agent_enabled,
    )


def _make_market() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime.now(UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("50000")},
        positions=[],
        account=None,
    )


def _render_messages_stub(**_kwargs: Any) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "stub-system"},
        {"role": "user", "content": "stub-user-prompt"},
    ]


async def _mb(container: Any, market: MarketSnapshot) -> str:
    return "stub-market-block"


async def _rt(container: Any) -> str:
    return "stub-recent-trades"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_not_invoked_when_flag_disabled(
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MULTI_AGENT_ENABLED=false ⇒ never build, never call the team."""
    calls: dict[str, int] = {"build": 0}

    def _fake_build(*_args: Any, **_kwargs: Any) -> Any:
        calls["build"] += 1
        return SimpleNamespace()

    monkeypatch.setattr(
        "omnitrade.agents.experts_team.build_agno_team", _fake_build
    )

    settings = _make_settings(
        multi_agent_enabled=False,
        strategy=StrategyName.AGGRESSIVE_TEAM,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AGGRESSIVE_TEAM,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    decision = await think(_make_market(), [])

    assert calls["build"] == 0
    assert "Team advisory" not in stub_agno.last_prompt
    # Defensive hold from the no-tool-fired path is fine — we only care
    # that the cycle completed without invoking the team.
    assert decision.action == "hold"


@pytest.mark.asyncio
async def test_team_not_invoked_for_non_team_strategy(
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with the flag on, non-team strategies skip the team path."""
    calls: dict[str, int] = {"build": 0}

    def _fake_build(*_args: Any, **_kwargs: Any) -> Any:
        calls["build"] += 1
        return SimpleNamespace()

    monkeypatch.setattr(
        "omnitrade.agents.experts_team.build_agno_team", _fake_build
    )

    settings = _make_settings(
        multi_agent_enabled=True,
        strategy=StrategyName.AI_AUTONOMOUS,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think(_make_market(), [])

    assert calls["build"] == 0
    assert "Team advisory" not in stub_agno.last_prompt


@pytest.mark.parametrize(
    "strategy",
    [StrategyName.AGGRESSIVE_TEAM, StrategyName.MULTI_AGENT_CONSENSUS],
)
@pytest.mark.asyncio
async def test_team_advisory_prepended_to_user_prompt(
    strategy: StrategyName,
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Team-eligible strategies see the verdict prepended to the user prompt."""
    build_calls: list[StrategyName] = []
    arun_prompts: list[str] = []

    class _StubTeam:
        async def arun(self, prompt: str) -> SimpleNamespace:
            arun_prompts.append(prompt)
            return SimpleNamespace(content="lean long BTC; confidence 0.7")

    def _fake_build(strat: StrategyName, *_args: Any, **_kwargs: Any) -> Any:
        build_calls.append(strat)
        return _StubTeam()

    monkeypatch.setattr(
        "omnitrade.agents.experts_team.build_agno_team", _fake_build
    )

    settings = _make_settings(multi_agent_enabled=True, strategy=strategy)
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=strategy,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think(_make_market(), [])

    assert build_calls == [strategy]
    assert arun_prompts == ["stub-user-prompt"]
    assert "Team advisory" in stub_agno.last_prompt
    assert "lean long BTC" in stub_agno.last_prompt
    # Original user prompt must still be present after the advisory header.
    assert "stub-user-prompt" in stub_agno.last_prompt


@pytest.mark.asyncio
async def test_team_run_failure_soft_degrades(
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Team raises ⇒ main Agent still runs, no advisory injected."""

    class _BoomTeam:
        async def arun(self, prompt: str) -> SimpleNamespace:
            raise RuntimeError("simulated team failure")

    monkeypatch.setattr(
        "omnitrade.agents.experts_team.build_agno_team",
        lambda *a, **kw: _BoomTeam(),
    )

    settings = _make_settings(
        multi_agent_enabled=True,
        strategy=StrategyName.AGGRESSIVE_TEAM,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AGGRESSIVE_TEAM,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    decision = await think(_make_market(), [])

    # Cycle still completes; advisory header absent because the team failed.
    assert decision.action == "hold"
    assert "Team advisory" not in stub_agno.last_prompt


@pytest.mark.asyncio
async def test_team_build_failure_skips_advisory_subsequent_cycles(
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build error caches the failure so retries don't keep firing."""
    build_calls: list[int] = []

    def _fake_build(*_args: Any, **_kwargs: Any) -> Any:
        build_calls.append(1)
        raise RuntimeError("bad team config")

    monkeypatch.setattr(
        "omnitrade.agents.experts_team.build_agno_team", _fake_build
    )

    settings = _make_settings(
        multi_agent_enabled=True,
        strategy=StrategyName.AGGRESSIVE_TEAM,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AGGRESSIVE_TEAM,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think(_make_market(), [])
    await think(_make_market(), [])

    # Second cycle must reuse the cached build_failed=True, never retry.
    assert len(build_calls) == 1


def test_think_fn_exposes_mcp_bridge_attribute(
    stub_agno: type[_StubAgent],
) -> None:
    """The lifespan reaper relies on this attribute being set."""
    settings = _make_settings(
        multi_agent_enabled=False,
        strategy=StrategyName.AI_AUTONOMOUS,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    bridge = getattr(think, "mcp_bridge", None)
    assert bridge is not None
    assert isinstance(bridge, ta_mod.AgnoMCPBridge)


# ---------------------------------------------------------------------------
# T1 + T2 — Agno-native retries + session summaries kwargs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_built_with_native_retries(
    stub_agno: type[_StubAgent],
) -> None:
    """Each cycle constructs the Agent with retries=2 + exponential backoff.

    Replaces the prior ``asyncio.wait_for`` + try/except retry pattern
    around the LLM call. The outer ``_TEAM_RUN_TIMEOUT_SECONDS`` cap
    still applies; this is purely the per-call retry policy on transient
    upstream failures.
    """
    settings = _make_settings(
        multi_agent_enabled=False,
        strategy=StrategyName.AI_AUTONOMOUS,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think(_make_market(), [])

    assert stub_agno.last_kwargs.get("retries") == ta_mod._AGENT_RETRIES
    assert stub_agno.last_kwargs.get("exponential_backoff") is True


@pytest.mark.asyncio
async def test_session_summaries_enabled_only_when_session_db_wired(
    stub_agno: type[_StubAgent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enable_session_summaries`` rides on the same gate as session db.

    Without ``agno_postgres_url`` Agno has nowhere to persist a summary,
    so the kwarg stays absent — sending it would raise on the agent's
    first ``arun`` (the summariser writes through ``Agent.db``).
    """
    # 1. No postgres → no session_db → no session summaries.
    settings = _make_settings(
        multi_agent_enabled=False,
        strategy=StrategyName.AI_AUTONOMOUS,
    )
    think = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think(_make_market(), [])
    assert "enable_session_summaries" not in stub_agno.last_kwargs

    # 2. With a (mocked) session_db, enable_session_summaries=True is set.
    sentinel_db = object()
    monkeypatch.setattr(ta_mod, "_build_session_db", lambda _s: sentinel_db)

    settings2 = Settings(
        llm_api_key=SecretStr("test-key"),
        trading_strategy=StrategyName.AI_AUTONOMOUS.value,
        multi_agent_enabled=False,
        agno_postgres_url="postgresql://stub/stub",
    )
    think2 = ta_mod.build_agno_think_fn(
        container=None,
        settings=settings2,
        render_messages=_render_messages_stub,
        strategy=StrategyName.AI_AUTONOMOUS,
        market_block_builder=_mb,
        recent_trades_block_builder=_rt,
    )
    await think2(_make_market(), [])
    assert stub_agno.last_kwargs.get("db") is sentinel_db
    assert stub_agno.last_kwargs.get("enable_session_summaries") is True
    assert stub_agno.last_kwargs.get("add_history_to_context") is True
