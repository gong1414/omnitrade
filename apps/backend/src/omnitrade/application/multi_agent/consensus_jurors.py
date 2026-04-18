"""arena-tribunal 3 jurors — ``StructuredTool`` factories (Phase 8.5a).

Each factory produces a ``StructuredTool`` whose coroutine performs an
independent sub-LLM call wrapped in ``asyncio.wait_for`` against
``settings.expert_timeout_seconds``. Timeout raises
``MultiAgentDegradedError``; successful calls return a structured
verdict dict. The judge (main agent) aggregates the 3 jurors.

Roster evidence: ``tests/fixtures/frozen/baseline_decisions/case_21_tribunal_close_half.json``
enumerates exactly these 3 tool names with ``initiated_by: "judge"``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.agents.prompts.multi_agent import (
    RISK_ASSESSOR_PROMPT,
    TECHNICAL_ANALYST_PROMPT,
    TREND_ANALYST_PROMPT,
)
from omnitrade.application.multi_agent.errors import MultiAgentDegradedError
from omnitrade.application.multi_agent.team_experts import _extract_verdict
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


_STRATEGY_VALUE: str = StrategyName.MULTI_AGENT_CONSENSUS.value


class _SymbolArgs(BaseModel):
    """Args schema shared by every juror tool — single ``symbol`` arg."""

    symbol: str = Field(
        description="Trading symbol the juror should analyse (e.g. 'BTC').",
    )


def _build_juror_tool(
    *,
    name: str,
    description: str,
    system_prompt: str,
    llm: LLMClient,
    settings: Settings,
) -> StructuredTool:
    """Common factory shared by all 3 arena-tribunal jurors."""

    async def _call_juror(symbol: str) -> dict[str, Any]:
        correlation_id = uuid.uuid4().hex
        with_context(logger).info(
            "multi_agent.juror.invoke",
            juror=name,
            symbol=symbol,
            correlation_id=correlation_id,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请就 {symbol} 给出独立判断以供陪审团合议。"},
        ]
        try:
            response = await asyncio.wait_for(
                llm.complete(
                    messages=messages,
                    model=settings.llm_model_name,
                    temperature=0.2,
                ),
                timeout=settings.expert_timeout_seconds,
            )
        except TimeoutError as exc:
            raise MultiAgentDegradedError(
                strategy=_STRATEGY_VALUE,
                reason=(
                    f"{name} timeout after {settings.expert_timeout_seconds}s"
                ),
                correlation_id=correlation_id,
            ) from exc

        verdict, reasoning = _extract_verdict(response)
        return {
            "juror": name,
            "symbol": symbol,
            "verdict": verdict,
            "reasoning": reasoning,
            "correlation_id": correlation_id,
        }

    return StructuredTool.from_function(
        coroutine=_call_juror,
        name=name,
        description=description,
        args_schema=_SymbolArgs,
    )


def build_technical_analyst_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_juror_tool(
        name="technicalAnalyst",
        description="技术分析师 — 多时间框架技术指标与形态判断。输入 symbol，返回 verdict + reasoning。",
        system_prompt=TECHNICAL_ANALYST_PROMPT,
        llm=llm,
        settings=settings,
    )


def build_trend_analyst_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_juror_tool(
        name="trendAnalyst",
        description="趋势分析师 — 宏观趋势方向与阶段判断。输入 symbol，返回 verdict + reasoning。",
        system_prompt=TREND_ANALYST_PROMPT,
        llm=llm,
        settings=settings,
    )


def build_risk_assessor_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_juror_tool(
        name="riskAssessor",
        description="风险评估师 — 账户 / 组合 / 波动率风险约束。输入 symbol，返回 verdict + reasoning。",
        system_prompt=RISK_ASSESSOR_PROMPT,
        llm=llm,
        settings=settings,
    )


# Dispatch order matches ``initiated_by: judge`` sequence in
# ``case_21_tribunal_close_half.json``.
CONSENSUS_JUROR_BUILDERS: tuple[
    Callable[[LLMClient, Settings], StructuredTool],
    ...,
] = (
    build_technical_analyst_tool,
    build_trend_analyst_tool,
    build_risk_assessor_tool,
)


__all__ = [
    "CONSENSUS_JUROR_BUILDERS",
    "build_risk_assessor_tool",
    "build_technical_analyst_tool",
    "build_trend_analyst_tool",
]
