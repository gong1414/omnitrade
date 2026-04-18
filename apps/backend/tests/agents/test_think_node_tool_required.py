"""Phase 8.5b canary tests — strict ``tool_choice="required"`` contract.

These tests lock in the Phase 8.5b invariant: the minimal-prompt LLM branch
must always emit ``tool_calls``. If the upstream provider silently reverts
to content-JSON, the decision parser must raise
:class:`~omnitrade.agents.think_node.ToolCallRequiredError` instead of
attempting to rehydrate a Decision from ``message.content``.

Paired with:
  * ``tests/agents/test_think_node.py`` — primary think-node unit suite.
  * ``scripts/verify_deepseek_tool_choice.py`` — live pre-merge DeepSeek
    check that ``tool_choice="required"`` is actually honored by the
    real LiteLLM + DeepSeek stack (G-2 gate).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from omnitrade.agents.think_node import (
    ToolCallRequiredError,
    _decision_from_llm_response,
)
from omnitrade.domain.entities import Decision

# ── content-only response → ToolCallRequiredError ───────────────────────── #


def test_content_only_response_raises_tool_call_required_error() -> None:
    """Response with ``{"action": "hold"}`` in ``content`` (no tool_calls)
    must raise ``ToolCallRequiredError`` — the Phase 8.5b fallback removal.
    """
    response: dict[str, Any] = {
        "model": "deepseek/deepseek-v3.2-exp",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"action": "hold"}),
                    # no tool_calls field
                },
                "finish_reason": "stop",
            }
        ],
    }

    with pytest.raises(ToolCallRequiredError) as exc_info:
        _decision_from_llm_response(response)

    assert exc_info.value.model == "deepseek/deepseek-v3.2-exp"
    assert "tool_choice='required'" in str(exc_info.value)


def test_empty_message_raises_tool_call_required_error() -> None:
    """A bare message with neither tool_calls nor content still errors cleanly."""
    response: dict[str, Any] = {
        "choices": [{"index": 0, "message": {"role": "assistant"}}],
    }
    with pytest.raises(ToolCallRequiredError) as exc_info:
        _decision_from_llm_response(response)
    # no ``model`` field → default ``unknown``
    assert exc_info.value.model == "unknown"


def test_null_content_and_missing_tool_calls_raises() -> None:
    """``content: null`` without tool_calls still triggers strict mode."""
    response: dict[str, Any] = {
        "model": "openai/gpt-4",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [],  # explicit empty list
                }
            }
        ],
    }
    with pytest.raises(ToolCallRequiredError):
        _decision_from_llm_response(response)


# ── tool_calls happy path → Decision ────────────────────────────────────── #


def test_response_with_tool_calls_parses_to_decision() -> None:
    """Normal ``tool_calls`` response still yields a Decision entity."""
    response: dict[str, Any] = {
        "model": "deepseek/deepseek-v3.2-exp",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_42",
                            "type": "function",
                            "function": {
                                "name": "hold",
                                "arguments": json.dumps({"reason": "flat market"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    decision = _decision_from_llm_response(response)
    assert isinstance(decision, Decision)
    assert decision.action == "hold"
    assert decision.reasoning == "flat market"


def test_response_with_open_position_tool_call_parses() -> None:
    """``openPosition`` tool call produces an open Decision."""
    response: dict[str, Any] = {
        "model": "deepseek/deepseek-v3.2-exp",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "openPosition",
                                "arguments": json.dumps(
                                    {
                                        "symbol": "BTC_USDT",
                                        "side": "long",
                                        "leverage": 10,
                                        "positionSizePercent": 20,
                                    }
                                ),
                            },
                        }
                    ],
                }
            }
        ],
    }
    decision = _decision_from_llm_response(response)
    assert decision.action == "open"
    assert decision.symbol == "BTC_USDT"
    assert decision.side == "long"
