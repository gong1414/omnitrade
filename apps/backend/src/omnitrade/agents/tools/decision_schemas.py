"""Decision-recorder tools for the Agno Agent (Phase 2 Agno migration).

The legacy LangChain `StructuredTool` versions in `trade_execution.py` couple
schema declaration with side-effecting trade execution. The Agno path
**separates concerns**:

  * The 4 decision tools here are *pure recorders*. When the LLM picks one,
    Agno fires the corresponding async function which captures the LLM's
    intent into a `DecisionRecorder` and returns a small acknowledgement
    payload. Real trade execution still happens in step 5 of the trading
    loop (`_build_execute_fn`), exactly like today.

  * Once `agent.arun(...)` returns, the recorder holds a `Decision` (or None
    if the LLM declined to call any of these tools — which we then resolve
    to `Decision(action="hold")`).

This shape keeps the Agno path schema-equivalent to the LangGraph parser at
`agents/think_node.py::_parse_decision_from_tool_call`, so swapping is
behavior-preserving on the structured-output contract (PR-B2 Phase C).

Per spec exception E2 the agent runs `deepseek-reasoner` with tool calling
in thinking mode — these tool functions must not raise; emitted errors
become tool-result strings the model can read.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import structlog

from omnitrade.agents.tools.structured_reason import StructuredReason
from omnitrade.domain.entities import Decision
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class DecisionRecorder:
    """Stateful holder shared between the 4 decision tools and the caller.

    Each `build_agno_think_fn` invocation creates a fresh recorder per
    cycle so concurrent cycles never cross-talk.
    """

    def __init__(self) -> None:
        self.decision: Decision | None = None
        self.fired_tool: str | None = None
        self.fire_count: int = 0

    def _record(self, decision: Decision, tool_name: str) -> None:
        self.decision = decision
        self.fired_tool = tool_name
        self.fire_count += 1
        with_context(logger).info(
            "decision_recorder.captured",
            tool=tool_name,
            action=decision.action,
            symbol=decision.symbol,
            fire_count=self.fire_count,
        )


# Type alias for an Agno-compatible decision tool callable.
DecisionTool = Callable[..., Awaitable[dict[str, Any]]]


def _structured_from_arg(reason: Any) -> StructuredReason | None:
    """Coerce the `reason` arg (StructuredReason | dict | str | None) to a
    StructuredReason or None. The Agno tool boundary may pass dicts since
    the JSON schema is built from type hints; pydantic models in args also
    arrive cleanly when Agno's tool registration handles BaseModel args."""
    if reason is None:
        return None
    if isinstance(reason, StructuredReason):
        return reason
    if isinstance(reason, dict):
        try:
            return StructuredReason.model_validate(reason)
        except Exception:  # noqa: BLE001 — defensive; non-fatal in Phase 2
            return None
    return None


def _decimal_or_none(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return None


def build_decision_tools(recorder: DecisionRecorder) -> list[DecisionTool]:
    """Return the 4 decision-recorder tools wired to a fresh recorder.

    Order matters: hold_tool last to counter recency bias (PR-B2 Phase A
    pre-mortem item M1). The Agno Agent will see them in this order.
    """

    async def open_position(
        symbol: str,
        side: str,
        size: float,
        leverage: int,
        reason: dict[str, Any] | StructuredReason,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        """Open a new leveraged futures position (decision recorder).

        Args:
            symbol: Trading pair, e.g. 'BTC_USDT'.
            side: 'long' or 'short'.
            size: Position size in contracts.
            leverage: Leverage multiplier in [1, 125].
            reason: StructuredReason capturing the structured-output contract.
            stop_loss: Optional stop-loss price.
            take_profit: Optional take-profit price.
        """
        structured = _structured_from_arg(reason)
        decision = Decision(
            action="open",
            symbol=str(symbol),
            side=str(side),
            leverage=int(leverage),
            size=_decimal_or_none(size),
            stop_loss=_decimal_or_none(stop_loss),
            take_profit=_decimal_or_none(take_profit),
            confidence=(
                Decimal(str(structured.confidence)) if structured and structured.confidence is not None else None
            ),
            reasoning=(structured.justification if structured else "open_position"),
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
            justification=structured.justification if structured else None,
        )
        recorder._record(decision, "open_position")
        return {"recorded": True, "action": "open", "symbol": symbol, "side": side}

    async def close_position(
        symbol: str,
        reason: dict[str, Any] | StructuredReason,
    ) -> dict[str, Any]:
        """Fully close an open position (100%)."""
        structured = _structured_from_arg(reason)
        decision = Decision(
            action="close",
            symbol=str(symbol),
            close_percentage=Decimal(100),
            reasoning=(structured.justification if structured else "close_position"),
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
            justification=structured.justification if structured else None,
        )
        recorder._record(decision, "close_position")
        return {"recorded": True, "action": "close", "symbol": symbol}

    async def partial_close(
        symbol: str,
        percentage: float,
        reason: dict[str, Any] | StructuredReason,
        new_stop_loss: float | None = None,
    ) -> dict[str, Any]:
        """Partially close an open position (pct in (0, 100])."""
        structured = _structured_from_arg(reason)
        pct = Decimal(str(percentage)) if percentage is not None else Decimal(50)
        decision = Decision(
            action="partial_close",
            symbol=str(symbol),
            close_percentage=pct,
            stop_loss=_decimal_or_none(new_stop_loss),
            reasoning=(structured.justification if structured else "partial_close"),
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
            justification=structured.justification if structured else None,
        )
        recorder._record(decision, "partial_close")
        return {"recorded": True, "action": "partial_close", "symbol": symbol, "percentage": float(pct)}

    async def hold_tool(
        reason: dict[str, Any] | StructuredReason,
    ) -> dict[str, Any]:
        """No-action decision. Use ONLY when 3+ absent factors enumerated."""
        structured = _structured_from_arg(reason)
        decision = Decision(
            action="hold",
            reasoning=(structured.justification if structured else "hold"),
            market_context=structured.market_context if structured else None,
            gates_passed=structured.gates_passed if structured else None,
            invalidation_condition=structured.invalidation_condition if structured else None,
            plan=structured.plan.model_dump() if structured and structured.plan else None,
            structured_confidence=structured.confidence if structured else None,
            output_language=structured.output_language if structured else None,
            justification=structured.justification if structured else None,
        )
        recorder._record(decision, "hold_tool")
        return {"recorded": True, "action": "hold"}

    # hold_tool LAST — counters LLM recency bias toward "hold" choices.
    return [open_position, close_position, partial_close, hold_tool]


__all__ = ["DecisionRecorder", "DecisionTool", "build_decision_tools"]
