"""LiteLLM client tests — mocked acompletion (no live API calls).

Protocol compliance: isinstance(client, LLMClient) is True.
Tests both prompt branches (minimal vs full World-class Trader).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnitrade.agents.prompts.system import (
    FULL_SYSTEM_PROMPT_TEMPLATE,
    MINIMAL_SYSTEM_PROMPT_TEMPLATE,
    format_system_prompt,
)
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import LLMClient
from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient

# Canonical sentinel strings that distinguish each branch.
# These are substrings present in each template that do NOT appear in the other.
# PR-B2 Phase B rewrote prompts into English — sentinels updated accordingly.
_MINIMAL_SENTINEL = "SYSTEM HARD RISK FLOOR"  # unique to MINIMAL_SYSTEM_PROMPT_TEMPLATE
_FULL_SENTINEL = "world-class systematic quantitative trader"  # unique to FULL_SYSTEM_PROMPT_TEMPLATE


def _build_messages(strategy: StrategyName, user_content: str) -> list[dict[str, str]]:
    """Inline helper: build a messages list for LLMClient.complete()."""
    return [
        {"role": "system", "content": format_system_prompt(strategy)},
        {"role": "user", "content": user_content},
    ]


# ── Prompt template tests ─────────────────────────────────────────────────


def test_ai_autonomous_gets_minimal_prompt() -> None:
    prompt = format_system_prompt(StrategyName.AI_AUTONOMOUS)
    assert _MINIMAL_SENTINEL in prompt
    assert _FULL_SENTINEL not in prompt


def test_alpha_beta_gets_minimal_prompt() -> None:
    prompt = format_system_prompt(StrategyName.ALPHA_BETA)
    assert _MINIMAL_SENTINEL in prompt
    assert _FULL_SENTINEL not in prompt


@pytest.mark.parametrize(
    "strategy",
    [
        StrategyName.CONSERVATIVE,
        StrategyName.BALANCED,
        StrategyName.AGGRESSIVE,
        StrategyName.AGGRESSIVE_TEAM,
        StrategyName.ULTRA_SHORT,
        StrategyName.SWING_TREND,
        StrategyName.MEDIUM_LONG,
        StrategyName.REBATE_FARMING,
        StrategyName.MULTI_AGENT_CONSENSUS,
    ],
)
def test_non_autonomous_strategies_get_full_prompt(strategy: StrategyName) -> None:
    prompt = format_system_prompt(strategy)
    assert _FULL_SENTINEL in prompt
    assert _MINIMAL_SENTINEL not in prompt


def test_build_messages_structure() -> None:
    msgs = _build_messages(StrategyName.CONSERVATIVE, "market data here")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "market data here"


def test_minimal_prompt_template_differs_from_full() -> None:
    """The two template branches are distinct texts."""
    assert MINIMAL_SYSTEM_PROMPT_TEMPLATE != FULL_SYSTEM_PROMPT_TEMPLATE
    assert _MINIMAL_SENTINEL in MINIMAL_SYSTEM_PROMPT_TEMPLATE
    assert _FULL_SENTINEL in FULL_SYSTEM_PROMPT_TEMPLATE


# ── Protocol compliance ────────────────────────────────────────────────────


def test_litellm_client_implements_protocol() -> None:
    """LiteLLMClient must satisfy isinstance(x, LLMClient)."""
    client = LiteLLMClient(model="deepseek/deepseek-v3.2-exp")
    assert isinstance(client, LLMClient)


# ── complete() mock tests ──────────────────────────────────────────────────


def _make_mock_response() -> Any:
    """Create a fake litellm ModelResponse-like object."""
    mock = MagicMock()
    mock.model_dump.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "deepseek/deepseek-v3.2-exp",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"action": "hold", "reasoning": "market unclear"}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    return mock


async def test_complete_returns_dict() -> None:
    """complete() returns a plain dict (decoupled from litellm types)."""
    client = LiteLLMClient(model="deepseek/deepseek-v3.2-exp")
    mock_resp = _make_mock_response()

    with patch("omnitrade.infrastructure.llm.litellm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)
        result = await client.complete(
            messages=[{"role": "user", "content": "analyze BTC"}],
        )

    assert isinstance(result, dict)
    assert "choices" in result


async def test_complete_with_tools() -> None:
    """complete() passes tools to litellm.acompletion."""
    client = LiteLLMClient(model="deepseek/deepseek-v3.2-exp")
    mock_resp = _make_mock_response()

    tools = [{"type": "function", "function": {"name": "open_position", "parameters": {}}}]

    with patch("omnitrade.infrastructure.llm.litellm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)
        await client.complete(
            messages=[{"role": "user", "content": "trade"}],
            tools=tools,
        )
        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert "tools" in call_kwargs


async def test_complete_model_override() -> None:
    """complete() respects model override argument."""
    client = LiteLLMClient(model="deepseek/deepseek-v3.2-exp")
    mock_resp = _make_mock_response()

    with patch("omnitrade.infrastructure.llm.litellm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)
        await client.complete(
            messages=[{"role": "user", "content": "test"}],
            model="openai/gpt-4",
        )
        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "openai/gpt-4"


async def test_rate_limit_error_propagates() -> None:
    """RateLimitError must NOT be caught — Phase 5 applies backoff."""
    import litellm as ll

    client = LiteLLMClient(model="deepseek/deepseek-v3.2-exp")

    with patch("omnitrade.infrastructure.llm.litellm_client.litellm") as mock_litellm:
        mock_litellm.acompletion = AsyncMock(
            side_effect=ll.RateLimitError(
                message="rate limit", llm_provider="deepseek", model="deepseek-v3"
            )
        )
        mock_litellm.RateLimitError = ll.RateLimitError
        with pytest.raises(ll.RateLimitError):
            await client.complete(messages=[{"role": "user", "content": "test"}])


def test_from_settings() -> None:
    """from_settings() wires model + api_key correctly."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.llm_model_name = "deepseek/deepseek-v3"
    settings.llm_api_key = MagicMock()
    settings.llm_api_key.get_secret_value.return_value = "sk-test"
    settings.deepseek_api_key = None
    settings.llm_base_url = None

    client = LiteLLMClient.from_settings(settings)
    assert client._model == "deepseek/deepseek-v3"
    assert client._api_key == "sk-test"
