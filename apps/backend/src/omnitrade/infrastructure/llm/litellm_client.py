"""LiteLLMClient — implements LLMClient protocol via litellm.acompletion.

Reads Settings for provider, api_key, base_url, model_name.
Supports DeepSeek (default), OpenRouter, Anthropic, OpenAI.
Cassette tests use vcrpy under tests/infrastructure/llm/cassettes/.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from omnitrade.config import Settings

import litellm
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class LiteLLMClient:
    """LLMClient implementation backed by litellm.acompletion.

    Args:
        model: Full model identifier e.g. 'deepseek/deepseek-v3.2-exp'.
        api_key: Provider API key. If None, reads from environment.
        base_url: Optional override base URL (for OpenAI-compat endpoints).
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        # Set litellm API key in environment if provided
        if api_key:
            # litellm reads from env; set provider-specific var if recognisable
            provider = model.split("/")[0] if "/" in model else ""
            if provider == "deepseek":
                os.environ["DEEPSEEK_API_KEY"] = api_key
            elif provider in ("openai", "gpt"):
                os.environ["OPENAI_API_KEY"] = api_key
            elif provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = api_key
            else:
                os.environ["OPENAI_API_KEY"] = api_key  # openrouter compat

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]:
        """Call litellm.acompletion and return the raw response dict.

        Args:
            messages: OpenAI-style messages list.
            model: Override model (uses self._model if None).
            temperature: Sampling temperature.
            tools: Optional tool definitions for function calling.
            tool_choice: Optional tool-call policy ("auto" | "required" | "none").
                When None (default), the kwarg is omitted from the LiteLLM call so
                upstream behavior is preserved byte-exact. Phase 8.0 seam; Phase
                8.5b flips the call-site default to "required".

        Returns:
            litellm response as a dict (compatible with openai.types.ChatCompletion shape).

        Raises:
            litellm.RateLimitError: propagated so Phase 5 can apply backoff.
            litellm.APIConnectionError: propagated; do not swallow.
        """
        effective_model = model or self._model
        with_context(logger).info(
            "litellm_client.complete",
            model=effective_model,
            temperature=temperature,
            has_tools=tools is not None,
            tool_choice=tool_choice,
        )

        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
        }
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        # litellm.RateLimitError and APIConnectionError are intentionally NOT caught here.
        # Phase 5 scheduler applies exponential backoff on these exceptions.
        response = await litellm.acompletion(**kwargs)

        # Convert ModelResponse to plain dict so callers stay decoupled from litellm types
        if hasattr(response, "model_dump"):
            return dict(response.model_dump())
        return dict(response)

    @classmethod
    def from_settings(cls, settings: Settings) -> LiteLLMClient:
        """Construct a LiteLLMClient from a Settings instance.

        Reads: llm_model_name, llm_api_key, llm_base_url (or deepseek_api_key).
        """
        api_key: str | None = None
        if settings.llm_api_key is not None:
            api_key = settings.llm_api_key.get_secret_value()
        elif settings.deepseek_api_key is not None:
            api_key = settings.deepseek_api_key.get_secret_value()

        base_url: str | None = None
        if settings.llm_base_url is not None:
            base_url = str(settings.llm_base_url)

        return cls(
            model=settings.llm_model_name,
            api_key=api_key,
            base_url=base_url,
        )
