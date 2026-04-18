"""Roster dispatch tests (Phase 8.5a, CRITICAL-2).

Asserts ``roster_for_strategy`` returns the exact team / jury roster per
the ``initiated_by`` evidence in the frozen decision fixtures:

  * ``case_16_raidersquad_close.json`` — 4 ``initiated_by: main_agent`` experts.
  * ``case_21_tribunal_close_half.json`` — 3 ``initiated_by: judge`` jurors.

Any other strategy raises ``ValueError`` (defensive guard).
"""

from __future__ import annotations

from typing import Any

import pytest

from omnitrade.application.multi_agent.roster import roster_for_strategy
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName


class _StubLLM:
    """Minimal ``LLMClient``-shaped stub — roster factories never call us here."""

    async def complete(self, **_: Any) -> dict[str, Any]:
        raise AssertionError("roster_for_strategy should not invoke the LLM")


_TEAM_ROSTER = {
    "trendExpert",
    "predictionExpert",
    "moneyFlowExpert",
    "riskControlExpert",
}
_JURY_ROSTER = {"technicalAnalyst", "trendAnalyst", "riskAssessor"}


def _settings() -> Settings:
    return Settings(multi_agent_enabled=True)


def test_aggressive_team_returns_4_expert_roster() -> None:
    tools = roster_for_strategy(
        StrategyName.AGGRESSIVE_TEAM,
        llm=_StubLLM(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert len(tools) == 4
    assert {t.name for t in tools} == _TEAM_ROSTER


def test_multi_agent_consensus_returns_3_juror_roster() -> None:
    tools = roster_for_strategy(
        StrategyName.MULTI_AGENT_CONSENSUS,
        llm=_StubLLM(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert len(tools) == 3
    assert {t.name for t in tools} == _JURY_ROSTER


@pytest.mark.parametrize(
    "strategy",
    [
        StrategyName.BALANCED,
        StrategyName.AI_AUTONOMOUS,
        StrategyName.CONSERVATIVE,
        StrategyName.AGGRESSIVE,
        StrategyName.SWING_TREND,
        StrategyName.ULTRA_SHORT,
        StrategyName.MEDIUM_LONG,
        StrategyName.REBATE_FARMING,
        StrategyName.ALPHA_BETA,
    ],
)
def test_non_multi_agent_strategies_raise_value_error(
    strategy: StrategyName,
) -> None:
    with pytest.raises(ValueError, match="not a multi-agent strategy"):
        roster_for_strategy(
            strategy,
            llm=_StubLLM(),  # type: ignore[arg-type]
            settings=_settings(),
        )


def test_roster_order_matches_fixture_initiated_by_sequence() -> None:
    """Dispatch order must match ``case_16_raidersquad_close.json``'s sequence."""
    tools = roster_for_strategy(
        StrategyName.AGGRESSIVE_TEAM,
        llm=_StubLLM(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert [t.name for t in tools] == [
        "trendExpert",
        "predictionExpert",
        "moneyFlowExpert",
        "riskControlExpert",
    ]

    jurors = roster_for_strategy(
        StrategyName.MULTI_AGENT_CONSENSUS,
        llm=_StubLLM(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert [t.name for t in jurors] == [
        "technicalAnalyst",
        "trendAnalyst",
        "riskAssessor",
    ]
