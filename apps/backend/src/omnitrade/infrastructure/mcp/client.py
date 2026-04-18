"""Async MCP JSON-RPC client over httpx.

The MCP wire format (per Model Context Protocol 2024-11) is JSON-RPC 2.0:

    POST <endpoint> HTTP/1.1
    content-type: application/json

    {"jsonrpc": "2.0", "id": "<uuid>", "method": "tools/call",
     "params": {"name": "<tool>", "arguments": { ... }}}

Success response::

    {"jsonrpc": "2.0", "id": "<uuid>", "result": { ... }}

Error response raises :class:`MCPRPCError` carrying ``code`` + ``message``.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class MCPRPCError(RuntimeError):
    """Raised when an MCP JSON-RPC call returns an error envelope."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"MCP JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPClient:
    """Minimal async MCP client.

    Args:
        endpoint: Fully-qualified HTTP(S) URL of the MCP server.
        timeout:  Per-request timeout (seconds). Default 15s.
        headers:  Extra HTTP headers (e.g. auth).
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("MCPClient: endpoint must not be empty")
        self._endpoint = endpoint
        self._timeout = timeout
        self._headers = {"content-type": "application/json", **(headers or {})}

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        method: str = "tools/call",
    ) -> dict[str, Any]:
        """Invoke an MCP tool.

        Args:
            tool_name: MCP tool identifier.
            arguments: Tool arguments payload (JSON-serialisable dict).
            method:    JSON-RPC method name; defaults to ``tools/call``.

        Returns:
            The ``result`` field of the JSON-RPC envelope.

        Raises:
            MCPRPCError:               on JSON-RPC error envelope.
            httpx.HTTPStatusError:     on 4xx/5xx HTTP status.
            httpx.TimeoutException:    on network timeout.
        """
        rpc_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": {"name": tool_name, "arguments": arguments or {}},
        }
        with_context(logger).info("mcp_client.call", tool=tool_name, rpc_id=rpc_id)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._endpoint, json=payload, headers=self._headers)
            response.raise_for_status()
            envelope = response.json()

        if not isinstance(envelope, dict):
            raise MCPRPCError(-32700, f"malformed envelope: {type(envelope).__name__}")
        if "error" in envelope:
            err = envelope["error"] or {}
            raise MCPRPCError(
                int(err.get("code", -32000)),
                str(err.get("message", "unknown MCP error")),
                err.get("data"),
            )
        result = envelope.get("result")
        if not isinstance(result, dict):
            # Upstream allows non-dict result shapes (lists, scalars); coerce.
            return {"result": result}
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        """Call ``tools/list`` and return the tool descriptor list."""
        rpc_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": rpc_id, "method": "tools/list", "params": {}}
        with_context(logger).info("mcp_client.list_tools", rpc_id=rpc_id)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._endpoint, json=payload, headers=self._headers)
            response.raise_for_status()
            envelope = response.json()
        if "error" in envelope:
            err = envelope["error"] or {}
            raise MCPRPCError(
                int(err.get("code", -32000)),
                str(err.get("message", "unknown MCP error")),
                err.get("data"),
            )
        result = envelope.get("result") or {}
        tools = result.get("tools") or []
        if not isinstance(tools, list):
            return []
        return [t for t in tools if isinstance(t, dict)]


__all__ = ["MCPClient", "MCPRPCError"]
