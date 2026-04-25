"""AgnoLLMAdapter — implements `LLMClient` via Agno's DeepSeek model.

Phase 1 of the Agno migration (`.omc/specs/deep-interview-agno-migration.md`,
plan: `~/.claude/plans/mossy-frolicking-hickey.md`).

Why this shape:
  - We adopt Agno's `agno.models.deepseek.DeepSeek` for **config / auth /
    base_url ownership** — the same model class Phase 2's Agno Agent will
    use, so by Phase 1 the model spec is already on Agno's side.
  - We then call the underlying `openai.AsyncOpenAI` client (which Agno
    builds for us via `get_async_client()`) directly. This returns an
    OpenAI-shaped `ChatCompletion`, which `model_dump()`s into the same
    dict layout `LiteLLMClient.complete` produces — so the `think_node`
    parser, `_parse_decision_from_tool_call()`, and every cassette test
    keeps working unchanged.
  - Per spec exception **E2** the default model id is `deepseek-reasoner`
    (Agno docs explicitly flag `deepseek-chat` tool calling as unstable;
    the trading loop is 100% tool-driven).

Rollback path:
  Settings field `agno_llm_enabled=False` (default) routes back to
  `LiteLLMClient`. The factory at `infrastructure/llm/factory.py` is the
  single decision seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from omnitrade.config import Settings

import structlog
from agno.models.deepseek import DeepSeek

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _strip_provider_prefix(model_id: str) -> str:
    """Drop the LiteLLM provider prefix (`deepseek/...`) when present."""
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


class AgnoLLMAdapter:
    """Adapter satisfying the `LLMClient` protocol via Agno's DeepSeek model."""

    def __init__(
        self,
        model_id: str = "deepseek-reasoner",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        # Drop any `deepseek/...` LiteLLM-style prefix — Agno's DeepSeek
        # constructor wants the bare model id.
        bare_id = _strip_provider_prefix(model_id)
        self._model_id = bare_id

        kwargs: dict[str, Any] = {"id": bare_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._model: DeepSeek = DeepSeek(**kwargs)
        self._client: AsyncOpenAI = self._model.get_async_client()

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]:
        """Same surface as `LiteLLMClient.complete`.

        Returns an OpenAI-shaped dict (via ChatCompletion.model_dump()) so
        downstream parsers — including `think_node._parse_decision_from_tool_call`
        — see exactly the keys they already expect (`choices[0].message.tool_calls`,
        `choices[0].message.content`, etc.).
        """
        effective_model = _strip_provider_prefix(model) if model else self._model_id
        with_context(logger).info(
            "agno_llm_adapter.complete",
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
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        # Note: openai.RateLimitError / APIConnectionError are intentionally
        # NOT caught here — Phase 5 scheduler applies exponential backoff,
        # mirroring the LiteLLM call-site contract.
        response = await self._client.chat.completions.create(**kwargs)

        if hasattr(response, "model_dump"):
            return dict(response.model_dump())
        return dict(response)

    @classmethod
    def from_settings(cls, settings: Settings) -> AgnoLLMAdapter:
        """Build from Settings; mirrors `LiteLLMClient.from_settings` so the
        factory can swap one for the other without touching callers."""
        api_key: str | None = None
        if settings.llm_api_key is not None:
            api_key = settings.llm_api_key.get_secret_value()
        elif settings.deepseek_api_key is not None:
            api_key = settings.deepseek_api_key.get_secret_value()

        base_url: str | None = None
        if settings.llm_base_url is not None:
            base_url = str(settings.llm_base_url)

        return cls(
            model_id=settings.agno_llm_model,
            api_key=api_key,
            base_url=base_url,
        )
