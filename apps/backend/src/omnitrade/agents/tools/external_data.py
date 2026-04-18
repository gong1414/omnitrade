"""External-data tool — thin passthrough to MCP-style JSON-RPC fetchers.

Phase 4.4 will plug the concrete MCP client in. For Phase 4.3 this module
exposes a builder that takes an ``async (endpoint: str, payload: dict)``
callable so the surface is stable whether the backend is httpx, an MCP
server, or a stub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


ExternalFetcher = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""``await fetcher(endpoint, payload)`` -> dict response."""


class ExternalDataArgs(BaseModel):
    endpoint: str = Field(description="External endpoint identifier (MCP tool name or URL).")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments payload sent to the external endpoint.",
    )


def build_external_data_tool(fetcher: ExternalFetcher) -> StructuredTool:
    async def _external_data(
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        with_context(logger).info("tool.external_data", endpoint=endpoint)
        return await fetcher(endpoint, payload)

    return StructuredTool.from_function(
        coroutine=_external_data,
        name="external_data",
        description=(
            "Call an external MCP-style data endpoint with a JSON payload and "
            "return the raw response. Use for on-chain, macro or social signals."
        ),
        args_schema=ExternalDataArgs,
    )


__all__ = ["ExternalDataArgs", "ExternalFetcher", "build_external_data_tool"]
