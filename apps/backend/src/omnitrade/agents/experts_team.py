"""Agno Team factory for multi-agent strategies.

Returns an Agno ``Team`` whose members are individual ``Agent`` objects,
each loaded with the corresponding system prompt from
``agents/prompts/multi_agent/``.

Two strategies use a Team today:

  * **AGGRESSIVE_TEAM** (`arena-raider-squad`) — 4 experts:
      `money_flow`, `prediction`, `risk_control`, `trend`.
  * **MULTI_AGENT_CONSENSUS** (`arena-tribunal`) — 3 jurors:
      `technical_analyst`, `trend_analyst`, `risk_assessor`.

The TeamMode is ``coordinate`` — the team leader orchestrates iterative
calls into members and synthesises the final response. Each sub-agent
shares the same Agno DeepSeek model instance (configured per Settings)
and a small set of MCP info tools so jurors / experts can fetch their
own market context if needed.

The Team is **advisory only**: it is invoked by
:func:`omnitrade.agents.trading_agent.build_agno_think_fn` whenever
``settings.multi_agent_enabled`` is true and the active strategy is one
of the two supported rosters. The Team's verdict is injected as context
into the main Agno Agent's user prompt; the Agent remains the sole
producer of the cycle's ``Decision`` via the ``DecisionRecorder`` tool
calls. Team failures soft-degrade — the Agent runs without advisory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import structlog
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from agno.team.mode import TeamMode
from agno.team.team import Team

from omnitrade.agents.prompts.multi_agent import (
    MONEY_FLOW_EXPERT_PROMPT,
    PREDICTION_EXPERT_PROMPT,
    RISK_CONTROL_EXPERT_PROMPT,
    TREND_EXPERT_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.risk_assessor import (
    SYSTEM_PROMPT as RISK_ASSESSOR_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.technical_analyst import (
    SYSTEM_PROMPT as TECHNICAL_ANALYST_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.trend_analyst import (
    SYSTEM_PROMPT as TREND_ANALYST_PROMPT,
)
from omnitrade.domain.enums import StrategyName

if TYPE_CHECKING:
    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)


_TEAM_LEADER_INSTRUCTIONS = """\
You are the team leader of a small panel of specialised analysts. Your job is to:

1. Read the user's situation report (market data + news + account + open positions).
2. Delegate the analysis to your members. Each member offers a focused
   perspective — combine them; do not echo a single member.
3. Synthesise a single, decisive verdict for the trading agent's main loop.

When you produce a final answer, structure it as:
  - A one-line directional call (e.g. "lean long BTC", "stay flat", "trim ETH").
  - Three short bullet points naming which member(s) most influenced the call.
  - The agreed confidence level in [0, 1].

Do NOT call any tools yourself; route to members. Do NOT make up data."""

_TEAM_RETRIES: int = 2
"""Per-run Agno-native retries on transient LLM failures inside the
advisory Team. The outer ``_TEAM_RUN_TIMEOUT_SECONDS`` cap in
``trading_agent.py`` still bounds wall-clock; this just gives the
coordinator a graceful retry path on a transient panel-member error
instead of soft-degrading the whole advisory."""

_MEMBER_RETRIES: int = 2
"""Per-call retries on each panel member Agent. The coordinator may
already retry the call to a member, but this catches in-member
transients (e.g. parser hiccups) before the coordinator sees them as
member-level failures."""


def _strip_provider_prefix(model_id: str) -> str:
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def _resolve_model(settings: Settings) -> DeepSeek:
    model_id = _strip_provider_prefix(settings.agno_llm_model)
    api_key: str | None = None
    if settings.llm_api_key is not None:
        api_key = settings.llm_api_key.get_secret_value()
    elif settings.deepseek_api_key is not None:
        api_key = settings.deepseek_api_key.get_secret_value()
    base_url = str(settings.llm_base_url) if settings.llm_base_url is not None else None
    kwargs: dict[str, Any] = {"id": model_id}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return DeepSeek(**kwargs)


def _build_member(
    *,
    name: str,
    role: str,
    instructions: str,
    model: DeepSeek,
    extra_tools: list[Any] | None = None,
) -> Agent:
    return Agent(
        name=name,
        role=role,
        model=model,
        instructions=instructions,
        tools=extra_tools or [],
        markdown=False,
        telemetry=False,
        retries=_MEMBER_RETRIES,
        exponential_backoff=True,
    )


def build_agno_team(
    strategy: StrategyName,
    settings: Settings,
    *,
    extra_tools: list[Any] | None = None,
) -> Team:
    """Return a fully wired Agno `Team` for ``strategy``.

    Args:
        strategy: Either `AGGRESSIVE_TEAM` (4-expert squad) or
            `MULTI_AGENT_CONSENSUS` (3-juror tribunal).
        settings: Settings instance — supplies model id + auth.
        extra_tools: Optional extra tools shared with every member (e.g. an
            `AgnoMCPBridge.toolset` so jurors can query market data).

    Raises:
        ValueError: If `strategy` is not one of the two supported values.
    """
    model = _resolve_model(settings)
    members: list[Agent] = []

    if strategy is StrategyName.AGGRESSIVE_TEAM:
        members = [
            _build_member(
                name="MoneyFlowExpert",
                role="capital flow / orderbook expert",
                instructions=MONEY_FLOW_EXPERT_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
            _build_member(
                name="PredictionExpert",
                role="forward-looking probability/forecast expert",
                instructions=PREDICTION_EXPERT_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
            _build_member(
                name="RiskControlExpert",
                role="position sizing / hard-floor risk expert",
                instructions=RISK_CONTROL_EXPERT_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
            _build_member(
                name="TrendExpert",
                role="multi-timeframe trend / momentum expert",
                instructions=TREND_EXPERT_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
        ]
        team_name = "RaiderSquad"
        team_description = "4 specialists analyse a setup; team leader synthesises."
    elif strategy is StrategyName.MULTI_AGENT_CONSENSUS:
        members = [
            _build_member(
                name="TechnicalAnalyst",
                role="juror 1/3 — technical/indicator perspective",
                instructions=TECHNICAL_ANALYST_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
            _build_member(
                name="TrendAnalyst",
                role="juror 2/3 — multi-timeframe trend perspective",
                instructions=TREND_ANALYST_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
            _build_member(
                name="RiskAssessor",
                role="juror 3/3 — account + portfolio risk perspective",
                instructions=RISK_ASSESSOR_PROMPT,
                model=model,
                extra_tools=extra_tools,
            ),
        ]
        team_name = "ArenaTribunal"
        team_description = "3-juror tribunal returns a directional vote with rationale."
    else:
        raise ValueError(
            f"build_agno_team: unsupported strategy {strategy!r}; "
            "expected AGGRESSIVE_TEAM or MULTI_AGENT_CONSENSUS"
        )

    # `members` is invariant in mypy's eye (`list[Agent | Team]`); cast so
    # the homogeneous Agent list satisfies the annotation at type-check
    # time without losing runtime correctness.
    team = Team(
        members=cast(Any, members),
        model=model,
        name=team_name,
        description=team_description,
        mode=TeamMode.coordinate,
        instructions=_TEAM_LEADER_INSTRUCTIONS,
        max_iterations=6,
        markdown=False,
        telemetry=False,
        retries=_TEAM_RETRIES,
    )
    logger.info(
        "experts_team.built",
        strategy=str(strategy),
        team=team_name,
        n_members=len(members),
    )
    return team


__all__ = ["build_agno_team"]
