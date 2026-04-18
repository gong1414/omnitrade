"""MCP (Model Context Protocol) — async JSON-RPC client + dynamic registry.

Phase 4.4 delivers three cooperating pieces:

  * ``client.MCPClient``        — async JSON-RPC over httpx; single method
    ``call(tool_name, args)`` returning a dict.
  * ``registry.MCPRegistry``    — dynamic name→callable map, hot-loaded
    from a config dict so the think node can discover MCP tools at runtime.
  * ``quality_tracker.ToolQualityTracker`` — per-tool success/latency
    counters with a ``should_call(name) -> bool`` gate so flaky external
    tools get demoted automatically.
"""

from __future__ import annotations

from omnitrade.infrastructure.mcp.client import MCPClient, MCPRPCError
from omnitrade.infrastructure.mcp.quality_tracker import ToolQualityTracker
from omnitrade.infrastructure.mcp.registry import MCPRegistry

__all__ = ["MCPClient", "MCPRPCError", "MCPRegistry", "ToolQualityTracker"]
