"""Sub-agent timeout budget tests (Phase 8.5a, MAJOR-3).

Each expert/juror handler wraps its ``llm.complete`` in
``asyncio.wait_for(timeout=settings.expert_timeout_seconds)``. A stubbed
LLM that sleeps longer than the budget must raise
``MultiAgentDegradedError`` within ``timeout + ε`` wall-clock seconds.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from omnitrade.application.multi_agent.consensus_jurors import (
    build_technical_analyst_tool,
)
from omnitrade.application.multi_agent.errors import MultiAgentDegradedError
from omnitrade.application.multi_agent.team_experts import (
    build_trend_expert_tool,
)
from omnitrade.config import Settings


class _SlowLLM:
    """LLM stub that sleeps ``delay_seconds`` before ever returning."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.calls = 0

    async def complete(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        await asyncio.sleep(self.delay_seconds)
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"verdict": "hold", "confidence": 0.5, "reasoning": ""}'
                    }
                }
            ]
        }


class _FastLLM:
    """LLM stub that returns immediately with a well-formed JSON verdict."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def complete(self, **_kwargs: Any) -> dict[str, Any]:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"verdict": "long", "confidence": 0.8, '
                            '"reasoning": "uptrend"}'
                        )
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_expert_timeout_raises_multi_agent_degraded_error() -> None:
    settings = Settings(
        multi_agent_enabled=True,
        expert_timeout_seconds=1,
    )
    # LLM sleeps 5s — budget is 1s, so wait_for must raise within ~1s.
    tool = build_trend_expert_tool(
        llm=_SlowLLM(delay_seconds=5.0),  # type: ignore[arg-type]
        settings=settings,
    )
    t0 = time.monotonic()
    with pytest.raises(MultiAgentDegradedError) as exc_info:
        await tool.ainvoke({"symbol": "BTC"})
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0, f"timeout budget overshot: {elapsed:.2f}s > 2s"
    assert exc_info.value.strategy == "arena-raider-squad"
    assert "trendExpert" in exc_info.value.reason
    assert "timeout" in exc_info.value.reason
    assert exc_info.value.correlation_id  # non-empty


@pytest.mark.asyncio
async def test_juror_timeout_raises_multi_agent_degraded_error() -> None:
    settings = Settings(
        multi_agent_enabled=True,
        expert_timeout_seconds=1,
    )
    tool = build_technical_analyst_tool(
        llm=_SlowLLM(delay_seconds=5.0),  # type: ignore[arg-type]
        settings=settings,
    )
    t0 = time.monotonic()
    with pytest.raises(MultiAgentDegradedError) as exc_info:
        await tool.ainvoke({"symbol": "BTC"})
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0
    assert exc_info.value.strategy == "arena-tribunal"
    assert "technicalAnalyst" in exc_info.value.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_ms", [50, 100, 500, 1000])
async def test_fast_llm_within_budget_returns_verdict(delay_ms: int) -> None:
    """Fuzz: delays between 50ms and 1s complete within the 15s budget."""
    settings = Settings(
        multi_agent_enabled=True,
        expert_timeout_seconds=15,
    )
    tool = build_trend_expert_tool(
        llm=_FastLLM(delay_seconds=delay_ms / 1000.0),  # type: ignore[arg-type]
        settings=settings,
    )
    result = await tool.ainvoke({"symbol": "ETH"})

    assert isinstance(result, dict)
    assert result["expert"] == "trendExpert"
    assert result["symbol"] == "ETH"
    assert result["verdict"] == "long"
    assert result["reasoning"]
    assert result["correlation_id"]


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_hold() -> None:
    """Defensive: non-JSON sub-LLM output collapses to ``hold`` verdict."""

    class _GarbledLLM:
        async def complete(self, **_kwargs: Any) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "not-json here"}}]}

    settings = Settings(multi_agent_enabled=True, expert_timeout_seconds=5)
    tool = build_trend_expert_tool(
        llm=_GarbledLLM(),  # type: ignore[arg-type]
        settings=settings,
    )
    result = await tool.ainvoke({"symbol": "BTC"})
    assert result["verdict"] == "hold"
    assert "not-json" in result["reasoning"]
