"""Tool layer for the think node.

MCP-managed tools are loaded via mcp2py (see mcp_tool_bridge).
Decision tool schemas are defined in trade_execution and parsed by
think_node._parse_decision_from_tool_call.
"""

from __future__ import annotations

from omnitrade.agents.tools.mcp_tool_bridge import (
    close_mcp_servers,
    load_mcp_servers,
    register_mcp_tools,
)
from omnitrade.agents.tools.trade_execution import (
    build_cancel_order_tool,
    build_close_position_tool,
    build_hold_tool,
    build_open_position_tool,
    build_partial_close_tool,
)

__all__ = [
    "build_cancel_order_tool",
    "build_close_position_tool",
    "build_hold_tool",
    "build_open_position_tool",
    "build_partial_close_tool",
    "close_mcp_servers",
    "load_mcp_servers",
    "register_mcp_tools",
]
