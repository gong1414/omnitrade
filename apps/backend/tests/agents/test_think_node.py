"""Unit tests for the think node (the only langgraph boundary)."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.agents.think_node import (
    ToolCallRequiredError,
    ToolRegistry,
    _decision_from_llm_response,
    _parse_decision_from_tool_call,
    build_think_graph,
    invoke_think,
)
from omnitrade.domain.entities import Decision


class _StubLLM:
    """In-memory ``LLMClient`` stub that returns a canned tool-call response."""

    def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
        self._tool_name = tool_name
        self._args = args
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"messages": messages, "model": model, "temperature": temperature})
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": self._tool_name,
                                    "arguments": json.dumps(self._args),
                                },
                            }
                        ],
                    },
                }
            ]
        }


# ── pure mapping helpers ────────────────────────────────────────────── #


def test_parse_open_position_tool_call() -> None:
    d = _parse_decision_from_tool_call(
        "openPosition",
        {"symbol": "BTC", "side": "long", "leverage": 15, "positionSizePercent": 20},
    )
    assert d.action == "open"
    assert d.symbol == "BTC"
    assert d.side == "long"
    assert d.leverage == 15
    assert d.size == Decimal("20")


def test_parse_close_full_tool_call() -> None:
    d = _parse_decision_from_tool_call("closePosition", {"symbol": "ETH", "percentage": 100})
    assert d.action == "close"
    assert d.close_percentage == Decimal(100)


def test_parse_close_partial_tool_call() -> None:
    d = _parse_decision_from_tool_call("closePosition", {"symbol": "ETH", "percentage": 50})
    assert d.action == "partial_close"
    assert d.close_percentage == Decimal(50)


def test_parse_hold_tool_call() -> None:
    d = _parse_decision_from_tool_call("hold", {"reason": "no_signal"})
    assert d.action == "hold"
    assert d.reasoning == "no_signal"


def test_parse_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        _parse_decision_from_tool_call("wipe_account", {})


def test_decision_from_llm_response_content_json_now_strict() -> None:
    """Phase 8.5b: content-JSON fallback is removed — must raise ToolCallRequiredError."""
    resp = {
        "model": "deepseek/deepseek-v3.2-exp",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"action": "hold", "reasoning": "flat market"}),
                }
            }
        ],
    }
    with pytest.raises(ToolCallRequiredError) as exc_info:
        _decision_from_llm_response(resp)
    assert exc_info.value.model == "deepseek/deepseek-v3.2-exp"


def test_decision_from_llm_response_no_tool_calls_raises() -> None:
    """Non-JSON content without tool_calls must raise ToolCallRequiredError."""
    with pytest.raises(ToolCallRequiredError):
        _decision_from_llm_response({"choices": [{"message": {"content": "not json"}}]})


# ── ToolRegistry ─────────────────────────────────────────────────────── #


@pytest.mark.asyncio
async def test_tool_registry_call_and_errors() -> None:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "args": args}

    reg = ToolRegistry()
    reg.register("noop", handler)
    assert reg.has("noop")
    assert reg.names() == ["noop"]
    result = await reg.call("noop", {"x": 1})
    assert result == {"ok": True, "args": {"x": 1}}
    with pytest.raises(KeyError):
        await reg.call("missing", {})


# ── graph build + invoke ────────────────────────────────────────────── #


@pytest.mark.asyncio
async def test_build_and_invoke_think_graph_open() -> None:
    llm = _StubLLM("openPosition", {"symbol": "BTC", "side": "long", "leverage": 10, "size": 1})
    graph = build_think_graph(llm, ToolRegistry(), model="stub-model")
    decision = await invoke_think(graph, [{"role": "user", "content": "what should I do?"}])

    assert isinstance(decision, Decision)
    assert decision.action == "open"
    assert decision.symbol == "BTC"
    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == "stub-model"


@pytest.mark.asyncio
async def test_build_and_invoke_think_graph_partial_close() -> None:
    llm = _StubLLM("closePosition", {"symbol": "SOL", "percentage": 30})
    graph = build_think_graph(llm, ToolRegistry(), model="stub-model")
    decision = await invoke_think(graph, [{"role": "user", "content": "manage position"}])

    assert decision.action == "partial_close"
    assert decision.close_percentage == Decimal(30)
