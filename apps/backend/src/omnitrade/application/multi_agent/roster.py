"""Strategy-dispatched roster assembly (Phase 8.5a, CRITICAL-2).

``roster_for_strategy`` is the single source of truth mapping a
``StrategyName`` to its ``StructuredTool`` roster:

  * ``AGGRESSIVE_TEAM``      → 4 ``team_experts``  (main_agent driven).
  * ``MULTI_AGENT_CONSENSUS`` → 3 ``consensus_jurors`` (judge driven).

Any other strategy raises ``ValueError`` — callers should gate on
``settings.multi_agent_enabled`` + strategy membership before reaching here.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from omnitrade.application.multi_agent.consensus_jurors import CONSENSUS_JUROR_BUILDERS
from omnitrade.application.multi_agent.team_experts import TEAM_EXPERT_BUILDERS
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient


def roster_for_strategy(
    strategy: StrategyName,
    *,
    llm: LLMClient,
    settings: Settings,
) -> list[StructuredTool]:
    """Return the multi-agent ``StructuredTool`` roster for ``strategy``.

    Raises:
        ValueError: If ``strategy`` is not one of the two multi-agent
            strategies. Defensive guard — caller should have gated on
            ``settings.multi_agent_enabled`` + strategy membership.
    """
    if strategy is StrategyName.AGGRESSIVE_TEAM:
        return [builder(llm, settings) for builder in TEAM_EXPERT_BUILDERS]
    if strategy is StrategyName.MULTI_AGENT_CONSENSUS:
        return [builder(llm, settings) for builder in CONSENSUS_JUROR_BUILDERS]
    raise ValueError(
        f"roster_for_strategy: {strategy!r} is not a multi-agent strategy"
    )


__all__ = ["roster_for_strategy"]
