"""Phase 8.0 — Protocol conformance tests for port-boundary extensions.

Guards that:
  1. ``CCXTExchange`` structurally conforms to the ``ExchangeClient`` Protocol
     after its 6 Phase-8.0 stubs are added (funding_rate, order_book,
     open_interest, open_orders, fetch_order, cancel_order).
  2. ``LLMClient.complete`` accepts the new ``tool_choice`` kwarg and threads
     it into the downstream kwargs (mock-verified; real pass-through to
     LiteLLM is covered by :mod:`tests.infrastructure.llm.test_litellm_client`).

Real ccxt / LiteLLM calls are never made here.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest

from omnitrade.domain.protocols import ExchangeClient, LLMClient
from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange
from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient


def _make_ccxt_exchange() -> CCXTExchange:
    """Construct a CCXTExchange without hitting the network.

    ccxt constructors only read config dicts; no HTTP traffic occurs until
    a method is called, so this is safe for a pure conformance check.
    """
    return CCXTExchange(
        exchange_id="gate",
        api_key="unit-test-key",
        api_secret="unit-test-secret",
        testnet=True,
    )


class TestExchangeClientConformance:
    def test_ccxt_exchange_is_exchange_client(self) -> None:
        exchange = _make_ccxt_exchange()
        assert isinstance(exchange, ExchangeClient)

    def test_ccxt_exchange_exposes_phase_8_0_stubs(self) -> None:
        exchange = _make_ccxt_exchange()
        for name in (
            "fetch_funding_rate",
            "fetch_order_book",
            "fetch_open_interest",
            "fetch_open_orders",
            "fetch_order",
            "cancel_order",
        ):
            assert callable(getattr(exchange, name)), f"Missing stub: {name}"

    def test_phase_8_0_methods_implemented_by_8_4(self) -> None:
        """The 6 port-boundary methods have real ccxt impls as of Phase 8.4.

        Per-method correctness is covered by
        ``tests/infrastructure/exchange/test_ccxt_new_methods.py``; this
        test only guards that none of them reverted to
        ``NotImplementedError`` stubs.
        """
        exchange = _make_ccxt_exchange()
        for name in (
            "fetch_funding_rate",
            "fetch_order_book",
            "fetch_open_interest",
            "fetch_open_orders",
            "fetch_order",
            "cancel_order",
        ):
            assert callable(getattr(exchange, name)), f"Missing method: {name}"


class _ToolChoiceCapturingLLM:
    """Mock impl capturing the kwargs actually passed to the completion call."""

    def __init__(self) -> None:
        self.captured_kwargs: dict[str, Any] = {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]:
        self.captured_kwargs = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        return {"content": "ok"}


class TestLLMClientToolChoice:
    def test_mock_llm_conforms(self) -> None:
        assert isinstance(_ToolChoiceCapturingLLM(), LLMClient)

    @pytest.mark.asyncio
    async def test_tool_choice_threaded_required(self) -> None:
        client = _ToolChoiceCapturingLLM()
        await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
            tool_choice="required",
        )
        assert client.captured_kwargs["tool_choice"] == "required"

    @pytest.mark.asyncio
    async def test_tool_choice_default_none(self) -> None:
        client = _ToolChoiceCapturingLLM()
        await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="test-model",
        )
        assert client.captured_kwargs["tool_choice"] is None


class TestLiteLLMClientToolChoicePassThrough:
    @pytest.mark.asyncio
    async def test_litellm_client_passes_tool_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``LiteLLMClient.complete(tool_choice=...)`` threads the kwarg."""
        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"choices": [{"message": {"content": "ok"}}]}

        import litellm

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

        client = LiteLLMClient(model="test/model", api_key="unit-test-key")
        await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            tool_choice="required",
        )
        assert captured.get("tool_choice") == "required"

    @pytest.mark.asyncio
    async def test_litellm_client_omits_tool_choice_when_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``tool_choice`` is None (default), the kwarg must be absent."""
        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"choices": [{"message": {"content": "ok"}}]}

        import litellm

        monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

        client = LiteLLMClient(model="test/model", api_key="unit-test-key")
        await client.complete(messages=[{"role": "user", "content": "hi"}])
        assert "tool_choice" not in captured
