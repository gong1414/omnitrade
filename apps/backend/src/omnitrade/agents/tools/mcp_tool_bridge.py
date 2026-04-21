"""mcp2py bridge — loads MCP servers and exposes tools to the ToolRegistry.

Replaces both the 9 direct StructuredTools and the AnyTool executor with
a single mcp2py layer.  All exchange / market / crypto tools are MCP servers
loaded via ``mcp2py.load()``.  Tool calls are direct (no LLM routing),
so latency stays low.

If mcp2py is not installed or servers fail to start, tools are silently
skipped — the agent still works with the 4 decision schemas.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def load_mcp_servers() -> list[Any]:
    """Load all MCP servers via mcp2py. Returns MCPServer instances.

    Each server is a long-lived subprocess (stdio transport).  mcp2py
    registers atexit cleanup handlers automatically.
    """
    try:
        import mcp2py  # type: ignore[import-untyped]
    except ImportError:
        with_context(logger).warning("mcp_tool_bridge.mcp2py_not_installed")
        return []

    servers: list[Any] = []

    for name, command in [
        (
            "omnitrade-trading",
            "python -m omnitrade.infrastructure.mcp.trading_mcp_server",
        ),
        (
            "omnitrade-crypto",
            "python -m omnitrade.infrastructure.data_sources.crypto_mcp_server",
        ),
    ]:
        try:
            srv = mcp2py.load(command, timeout=15)
            servers.append(srv)
            tool_names = list(srv._tools.keys())
            with_context(logger).info(
                "mcp_tool_bridge.server_loaded",
                server=name,
                tools=tool_names,
            )
        except Exception as exc:
            with_context(logger).warning(
                "mcp_tool_bridge.server_load_failed",
                server=name,
                error=str(exc),
            )

    return servers


def register_mcp_tools(
    servers: list[Any],
    tool_schemas: list[dict[str, Any]],
    registry: Any,
) -> int:
    """Register every MCP tool as a schema + handler.  Returns count registered."""
    registered = 0

    for server in servers:
        for tool_name, tool_def in server._tools.items():
            description = tool_def.get("description", "")
            input_schema = tool_def.get("inputSchema", {})

            # Register schema for the LLM (OpenAI function-calling format).
            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": input_schema,
                },
            })

            # Register handler — wraps sync mcp2py call in asyncio.to_thread.
            _make_handler(server, tool_name, registry)
            registered += 1

    return registered


def _make_handler(server: Any, tool_name: str, registry: Any) -> None:
    """Create and register an async handler that calls the MCP tool."""
    _server = server  # capture for closure
    _tool_name = tool_name

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = await asyncio.to_thread(
                getattr(_server, _tool_name),
                **{k: v for k, v in args.items() if v is not None},
            )
        except Exception as exc:
            with_context(logger).warning(
                "mcp_tool_bridge.call_failed",
                tool=_tool_name,
                error=str(exc),
            )
            return {"error": str(exc), "tool": _tool_name}

        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return {"result": raw}

    registry.register(_tool_name, _handler)


def close_mcp_servers(servers: list[Any]) -> None:
    """Gracefully shut down MCP server subprocesses."""
    for srv in servers:
        try:
            srv.close()
        except Exception:
            pass
