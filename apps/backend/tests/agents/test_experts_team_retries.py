"""Verify Agno-native retry kwargs are wired on the advisory Team.

Replaces the prior 'soft-degrade on first failure' pattern: a transient
LLM error inside the coordinator or a panel member used to nuke the
whole advisory and fall through to no-team mode. With ``retries=2`` on
both the Team and its members, transient failures get a free second
attempt before the soft-degrade kicks in.

These tests assert construction kwargs only — no live LLM call, no
network. We pull the resolved attributes off the Agno ``Agent`` /
``Team`` objects after construction.
"""

from __future__ import annotations

from pydantic import SecretStr

from omnitrade.agents.experts_team import (
    _MEMBER_RETRIES,
    _TEAM_RETRIES,
    build_agno_team,
)
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName


def _settings() -> Settings:
    return Settings(
        llm_api_key=SecretStr("test-key"),
        trading_strategy=StrategyName.MULTI_AGENT_CONSENSUS.value,
        multi_agent_enabled=True,
    )


def test_team_constructed_with_retries() -> None:
    team = build_agno_team(StrategyName.MULTI_AGENT_CONSENSUS, _settings())
    assert getattr(team, "retries", None) == _TEAM_RETRIES


def test_each_member_has_retries_and_backoff() -> None:
    team = build_agno_team(StrategyName.AGGRESSIVE_TEAM, _settings())
    members = list(getattr(team, "members", []))
    assert len(members) == 4, "AGGRESSIVE_TEAM should have 4 members"
    for m in members:
        assert getattr(m, "retries", None) == _MEMBER_RETRIES
        assert getattr(m, "exponential_backoff", False) is True
