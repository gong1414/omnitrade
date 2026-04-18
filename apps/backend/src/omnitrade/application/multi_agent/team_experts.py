"""arena-raider-squad 4 experts — ``StructuredTool`` factories (Phase 8.5a).

Each factory produces a ``StructuredTool`` whose coroutine performs an
independent sub-LLM call wrapped in ``asyncio.wait_for`` against
``settings.expert_timeout_seconds``. Timeout raises
``MultiAgentDegradedError``; successful calls return a structured
verdict dict that the main-agent consumer aggregates.

Roster evidence: ``tests/fixtures/frozen/baseline_decisions/case_16_raidersquad_close.json``
enumerates exactly these 4 tool names with ``initiated_by: "main_agent"``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.agents.prompts.multi_agent import (
    MONEY_FLOW_EXPERT_PROMPT,
    PREDICTION_EXPERT_PROMPT,
    RISK_CONTROL_EXPERT_PROMPT,
    TREND_EXPERT_PROMPT,
)
from omnitrade.application.multi_agent.errors import MultiAgentDegradedError
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


_STRATEGY_VALUE: str = StrategyName.AGGRESSIVE_TEAM.value


class _SymbolArgs(BaseModel):
    """Args schema shared by every expert tool — single ``symbol`` arg."""

    symbol: str = Field(
        description="Trading symbol the expert should analyse (e.g. 'BTC').",
    )


def _build_expert_tool(
    *,
    name: str,
    description: str,
    system_prompt: str,
    llm: LLMClient,
    settings: Settings,
) -> StructuredTool:
    """Common factory shared by all 4 arena-raider-squad experts."""

    async def _call_expert(symbol: str) -> dict[str, Any]:
        correlation_id = uuid.uuid4().hex
        with_context(logger).info(
            "multi_agent.expert.invoke",
            expert=name,
            symbol=symbol,
            correlation_id=correlation_id,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析 {symbol}，给出你的独立判断。"},
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
            "expert": name,
            "symbol": symbol,
            "verdict": verdict,
            "reasoning": reasoning,
            "correlation_id": correlation_id,
        }

    return StructuredTool.from_function(
        coroutine=_call_expert,
        name=name,
        description=description,
        args_schema=_SymbolArgs,
    )


def _extract_verdict(response: dict[str, Any]) -> tuple[str, str]:
    """Pull ``verdict`` + ``reasoning`` from the sub-LLM JSON response.

    Sub-agents emit ``{"verdict": "...", "confidence": ..., "reasoning": "..."}``
    in the ``content`` field. On malformed output fall back to ``hold`` /
    raw content so the main agent sees a stable shape.
    """
    choices = response.get("choices") or []
    if not choices:
        return "hold", "empty response"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        return "hold", "non-string content"
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return "hold", content[:120]
    verdict = str(payload.get("verdict") or "hold")
    reasoning = str(payload.get("reasoning") or "")
    if verdict not in {"long", "short", "hold"}:
        verdict = "hold"
    return verdict, reasoning


def build_trend_expert_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_expert_tool(
        name="trendExpert",
        description="趋势分析专家 — 多时间框架趋势方向判断。输入 symbol，返回 verdict + reasoning。",
        system_prompt=TREND_EXPERT_PROMPT,
        llm=llm,
        settings=settings,
    )


def build_prediction_expert_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_expert_tool(
        name="predictionExpert",
        description="预测专家 — 30分钟到4小时的短期方向预判。输入 symbol，返回 verdict + reasoning。",
        system_prompt=PREDICTION_EXPERT_PROMPT,
        llm=llm,
        settings=settings,
    )


def build_money_flow_expert_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_expert_tool(
        name="moneyFlowExpert",
        description="资金流专家 — 主力资金 / 资金费率 / 持仓量变化判断。输入 symbol，返回 verdict + reasoning。",
        system_prompt=MONEY_FLOW_EXPERT_PROMPT,
        llm=llm,
        settings=settings,
    )


def build_risk_control_expert_tool(llm: LLMClient, settings: Settings) -> StructuredTool:
    return _build_expert_tool(
        name="riskControlExpert",
        description="风险控制专家 — 账户回撤 / 杠杆 / 波动率约束。输入 symbol，返回 verdict + reasoning。",
        system_prompt=RISK_CONTROL_EXPERT_PROMPT,
        llm=llm,
        settings=settings,
    )


# Public tuple used by ``roster.py`` — keeps dispatch order deterministic
# (matches the ``initiated_by: main_agent`` sequence in
# ``case_16_raidersquad_close.json``).
TEAM_EXPERT_BUILDERS: tuple[
    Callable[[LLMClient, Settings], StructuredTool],
    ...,
] = (
    build_trend_expert_tool,
    build_prediction_expert_tool,
    build_money_flow_expert_tool,
    build_risk_control_expert_tool,
)


__all__ = [
    "TEAM_EXPERT_BUILDERS",
    "build_money_flow_expert_tool",
    "build_prediction_expert_tool",
    "build_risk_control_expert_tool",
    "build_trend_expert_tool",
]


# Silence "unused import" warnings for the intentional Awaitable alias used
# by the shared coroutine typing (StructuredTool introspects signatures).
_ = Awaitable
