"""Agent-layer error types (PR-B1 Step 4).

Companion to ``omnitrade.application.multi_agent.errors`` (which owns the
multi-agent orchestrator errors). This module owns parser/contract errors
that live at the ``agents/think_node`` boundary.
"""

from __future__ import annotations


class StructuredOutputContractError(Exception):
    """LLM tool call's reason field violated StructuredReason schema.

    Raised when ``args["reason"]`` is a dict but pydantic validation fails.
    No opt-out flag — Principle 4 ("loud failures"). Rollback via git revert
    only; do NOT add a ``strict_structured_output`` bypass flag.

    Attributes:
        tool_name: The tool name whose ``reason`` field failed validation.
        validation_error: The stringified ``pydantic.ValidationError`` message.
    """

    def __init__(self, tool_name: str, validation_error: str) -> None:
        super().__init__(
            f"Tool {tool_name!r} reason dict failed schema: {validation_error}"
        )
        self.tool_name = tool_name
        self.validation_error = validation_error


__all__ = ["StructuredOutputContractError"]
