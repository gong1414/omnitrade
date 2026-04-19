"""Think node — the ONLY file that imports from ``langgraph``.

Responsibilities (consensus plan §6 Phase 4.1):
  * Build a 1-node ``StateGraph`` that owns the LLM tool-calling loop.
  * Accept an ``LLMClient`` protocol + a ``ToolRegistry`` mapping via DI.
  * Emit a ``Decision`` domain entity as structured output.

Scope gate (§7 R9): ``rg -n 'from langgraph' src/omnitrade/ | grep -v
'agents/think_node.py' | wc -l`` MUST be zero.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, TypedDict

import structlog
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from omnitrade.agents.errors import StructuredOutputContractError
from omnitrade.agents.tools.structured_reason import StructuredReason
from omnitrade.domain.entities import Decision
from omnitrade.domain.protocols import LLMClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class ToolCallRequiredError(Exception):
    """LLM response missing required ``tool_calls`` — strict mode enabled.

    Raised by :func:`_decision_from_llm_response` when the upstream LLM
    returns a ``choices[0].message`` body without any ``tool_calls``. The
    minimal-prompt branch (``arena-autopilot`` / ``arena-dual-signal``) forces
    ``tool_choice="required"`` per Phase 8.5b; absent tool_calls signals
    a provider misconfiguration (or a silent drift to content-JSON) that
    the old fallback path used to mask. Rollback toggle:
    ``STRICT_TOOL_CALLS=false`` (see ``omnitrade.config.Settings``).
    """

    def __init__(self, model: str = "unknown") -> None:
        super().__init__(
            f"LLM ({model}) returned no tool_calls but "
            "tool_choice='required' was requested"
        )
        self.model = model


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    """In-memory map of tool-name to async handler.

    The think node is fed a registry (not concrete tools) so the boundary
    is testable with in-memory stubs. Phase 4.3/4.4 populate the registry
    with LangChain/MCP tools at wiring time.
    """

    def __init__(self, handlers: dict[str, ToolHandler] | None = None) -> None:
        self._handlers: dict[str, ToolHandler] = dict(handlers or {})

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def has(self, name: str) -> bool:
        return name in self._handlers

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._handlers:
            raise KeyError(f"ToolRegistry: no handler registered for {name!r}")
        return await self._handlers[name](args)

    def names(self) -> list[str]:
        return sorted(self._handlers.keys())


class ThinkState(TypedDict, total=False):
    """LangGraph state passed between the think-node steps."""

    messages: list[dict[str, Any]]
    decision: Decision | None
    tool_schemas: list[dict[str, Any]]
    raw_response: dict[str, Any]


def _parse_reason(
    name: str, args: dict[str, Any]
) -> tuple[str, StructuredReason | None]:
    """Dual-path reason parser (PR-B1 Step 4).

    Returns ``(reasoning_str, structured_or_none)``:

    * If ``args["reason"]`` is a **dict** → validate as :class:`StructuredReason`.
      On failure raise :class:`StructuredOutputContractError` (Principle 4 —
      loud failures, no opt-out flag).
    * If ``args["reason"]`` is a **str** → legacy flat path, no validation.
    * Anything else → defensive coerce to str, treat as legacy.

    The ``name`` parameter is forwarded to the error for observability.
    """
    raw_reason = args.get("reason", "")
    if isinstance(raw_reason, dict):
        try:
            structured = StructuredReason.model_validate(raw_reason)
        except ValidationError as exc:
            raise StructuredOutputContractError(
                tool_name=name,
                validation_error=str(exc),
            ) from exc
        return structured.justification, structured
    if isinstance(raw_reason, str):
        return raw_reason, None
    # Defensive: neither str nor dict — coerce and treat as legacy.
    return str(raw_reason), None


def _parse_decision_from_tool_call(tool_name: str, args: dict[str, Any]) -> Decision:
    """Translate an OpenAI-style tool call into a Decision entity.

    The agent exposes three primitive tools over the LLM boundary:
      * ``openPosition(symbol, side, leverage, positionSizePercent, ...)``
      * ``closePosition(symbol, percentage)``  (100 = full; <100 = partial)
      * ``hold()``
    This function is the single place that translates that shape to the
    ``Decision`` domain entity. The characterization gate depends on it.

    **Dual-path reasoning (PR-B1 Step 4)**:
    All four tool branches run ``_parse_reason`` so that when PR-B2 updates the
    tool schemas to emit ``reason: StructuredReason``, every branch is already
    capable of parsing the dict form. The legacy flat-string path remains
    supported for full backward compatibility (22-cassette gate).

    Multi-agent experts (``MultiAgentDegradedError`` / ``consensus_jurors`` /
    ``team_experts``) do NOT call ``_parse_decision_from_tool_call`` — they
    operate at the application/multi_agent layer and are ADR-exempt from this
    parser. No changes required there.
    """
    name = tool_name.strip()
    if name in {"hold_tool", "hold", "no_action"}:
        # PR-B2 Phase C: hold_tool is a real LLM tool — reason MUST be a dict
        # (StructuredReason). Legacy string fallback kept for cassette compat.
        raw_reason = args.get("reason", "")
        if not isinstance(raw_reason, dict) and not isinstance(raw_reason, str):
            raise StructuredOutputContractError(
                tool_name=name,
                validation_error=(
                    f"hold_tool 'reason' must be a StructuredReason dict, "
                    f"got {type(raw_reason).__name__}"
                ),
            )
        reasoning_str, structured = _parse_reason(name, args)
        return Decision(
            action="hold",
            reasoning=reasoning_str,
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
        )
    if name in {"openPosition", "open_position"}:
        reasoning_str, structured = _parse_reason(name, args)
        size = args.get("size") or args.get("positionSizePercent") or args.get("quantity")
        return Decision(
            action="open",
            symbol=str(args["symbol"]),
            side=str(args["side"]),
            leverage=int(args["leverage"]) if "leverage" in args else None,
            size=Decimal(str(size)) if size is not None else None,
            stop_loss=(
                Decimal(str(args["stop_loss"])) if args.get("stop_loss") is not None else None
            ),
            take_profit=(
                Decimal(str(args["take_profit"])) if args.get("take_profit") is not None else None
            ),
            confidence=(
                Decimal(str(args["confidence"])) if args.get("confidence") is not None else None
            ),
            reasoning=reasoning_str,
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
        )
    if name in {"closePosition", "close_position"}:
        reasoning_str, structured = _parse_reason(name, args)
        pct_raw = args.get("percentage")
        pct = Decimal(str(pct_raw)) if pct_raw is not None else Decimal(100)
        action = "partial_close" if pct < Decimal(100) else "close"
        return Decision(
            action=action,
            symbol=str(args["symbol"]),
            close_percentage=pct,
            reasoning=reasoning_str,
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
        )
    if name in {"partialClose", "partial_close_position"}:
        reasoning_str, structured = _parse_reason(name, args)
        pct_raw = args.get("percentage") or args.get("close_percentage")
        pct = Decimal(str(pct_raw)) if pct_raw is not None else Decimal(50)
        return Decision(
            action="partial_close",
            symbol=str(args["symbol"]),
            close_percentage=pct,
            reasoning=reasoning_str,
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
        )
    raise ValueError(f"Unknown tool name for decision mapping: {name!r}")


def _decision_from_llm_response(response: dict[str, Any]) -> Decision:
    """Extract a ``Decision`` from a raw LLM response dict.

    Only the upstream-compatible tool-calling shape is accepted
    (``choices[0].message.tool_calls[0]``). Phase 8.5b deleted the
    silent ``content``-JSON fallback: when ``tool_calls`` is absent we
    raise :class:`ToolCallRequiredError` instead of attempting to parse
    ``message.content``. This guarantees that any minimal-prompt cycle
    running with ``tool_choice="required"`` fails loudly on provider
    misconfiguration rather than papering over it.
    """
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("LLM response missing 'choices'")
    msg = choices[0].get("message") or {}
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        first = tool_calls[0]
        fn = first.get("function") or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or {}
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        return _parse_decision_from_tool_call(name, args)

    model_name = str(response.get("model") or "unknown")
    raise ToolCallRequiredError(model=model_name)


def build_think_graph(
    llm: LLMClient,
    registry: ToolRegistry,
    *,
    model: str,
    temperature: float = 0.2,
    max_tool_iterations: int = 3,
) -> Any:
    """Build the 1-node LangGraph for the ``think`` phase.

    Args:
        llm: Protocol-typed LLM client (LiteLLM adapter in prod, stub in tests).
        registry: Tool registry that maps tool names to async handlers.
        model: Model id to pass to ``llm.complete``.
        temperature: Sampling temperature. Low default for parity determinism.
        max_tool_iterations: Hard cap on think→tool→think loops.

    Returns:
        A compiled LangGraph that, when invoked with ``{"messages": [...]}``,
        populates ``state['decision']`` with a ``Decision`` entity.
    """
    tool_schemas: list[dict[str, Any]] = []  # Phase 4.3 injects real JSON schemas

    async def _think(state: ThinkState) -> ThinkState:
        messages = state.get("messages") or []
        with_context(logger).info("think_node.call_llm", n_messages=len(messages), model=model)
        response = await llm.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=tool_schemas or None,
        )
        return {"messages": messages, "raw_response": response}

    async def _decide(state: ThinkState) -> ThinkState:
        response = state.get("raw_response") or {}
        decision = _decision_from_llm_response(response)
        with_context(logger).info(
            "think_node.decision",
            action=decision.action,
            symbol=decision.symbol,
        )
        return {**state, "decision": decision}

    graph: StateGraph[ThinkState] = StateGraph(ThinkState)
    graph.add_node("think", _think)
    graph.add_node("decide", _decide)
    graph.set_entry_point("think")
    graph.add_edge("think", "decide")
    graph.add_edge("decide", END)
    compiled = graph.compile()
    # Keep the iteration cap accessible for tests / introspection.
    compiled._think_max_iters = max_tool_iterations  # type: ignore[attr-defined]
    compiled._registry = registry  # type: ignore[attr-defined]
    return compiled


async def invoke_think(
    compiled_graph: Any,
    messages: list[dict[str, Any]],
) -> Decision:
    """Convenience wrapper: invoke the compiled think graph and return a Decision.

    Raises:
        ValueError: If the graph returned no decision (malformed LLM response).
    """
    result = await compiled_graph.ainvoke({"messages": messages})
    decision = result.get("decision") if isinstance(result, dict) else None
    if decision is None:
        raise ValueError("think graph did not produce a Decision")
    if not isinstance(decision, Decision):
        raise TypeError(f"think graph returned non-Decision value: {type(decision).__name__}")
    return decision


__all__ = [
    "StructuredOutputContractError",
    "ToolCallRequiredError",
    "ToolHandler",
    "ToolRegistry",
    "build_think_graph",
    "invoke_think",
]
