"""Agent-layer error types.

Owns parser/contract errors raised when an LLM tool-call payload fails
the :class:`StructuredReason` schema. The Agno DecisionRecorder tools in
:mod:`omnitrade.agents.tools.decision_schemas` raise these so the cycle
fails loudly instead of silently dropping malformed reasoning.
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
        super().__init__(f"Tool {tool_name!r} reason dict failed schema: {validation_error}")
        self.tool_name = tool_name
        self.validation_error = validation_error


__all__ = ["StructuredOutputContractError"]
