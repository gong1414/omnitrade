"""Dynamic MCP tool registry.

The registry maps a flat ``tool_name`` to an ``MCPClient + descriptor``
pair. It is hot-loaded from a config dict so the think node can discover
new MCP tools without a deploy. Lookup is O(1); iteration is name-sorted
for deterministic logging.

Schema of a config entry::

    {
        "name": "onchain_eth_gas",
        "endpoint": "https://mcp.example.com/rpc",
        "description": "current Ethereum gas snapshot",
        "headers": {"x-api-key": "..."},   # optional
        "timeout": 10.0                     # optional, seconds
    }
"""

from __future__ import annotations

from typing import Any

import structlog

from omnitrade.infrastructure.mcp.client import MCPClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class MCPRegistry:
    """Flat registry of MCP tools keyed by unique tool name."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._descriptors: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        endpoint: str,
        *,
        description: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not name:
            raise ValueError("MCPRegistry: tool name must not be empty")
        self._clients[name] = MCPClient(endpoint=endpoint, timeout=timeout, headers=headers)
        self._descriptors[name] = {
            "name": name,
            "endpoint": endpoint,
            "description": description,
        }
        with_context(logger).info("mcp_registry.register", name=name, endpoint=endpoint)

    def load_from_config(self, config: list[dict[str, Any]]) -> None:
        """Load a list of tool configs (see module docstring for schema)."""
        for entry in config:
            if not isinstance(entry, dict):
                with_context(logger).warning("mcp_registry.skip_non_dict", entry=repr(entry)[:80])
                continue
            name = entry.get("name")
            endpoint = entry.get("endpoint")
            if not name or not endpoint:
                with_context(logger).warning(
                    "mcp_registry.skip_incomplete",
                    keys=sorted(entry.keys()),
                )
                continue
            self.register(
                str(name),
                str(endpoint),
                description=str(entry.get("description") or ""),
                headers=entry.get("headers"),
                timeout=float(entry.get("timeout", 15.0)),
            )

    def has(self, name: str) -> bool:
        return name in self._clients

    def names(self) -> list[str]:
        return sorted(self._clients.keys())

    def descriptor(self, name: str) -> dict[str, Any]:
        if name not in self._descriptors:
            raise KeyError(f"MCPRegistry: no tool {name!r}")
        return dict(self._descriptors[name])

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self._clients:
            raise KeyError(f"MCPRegistry: no tool {name!r}")
        client = self._clients[name]
        return await client.call(name, arguments or {})


__all__ = ["MCPRegistry"]
