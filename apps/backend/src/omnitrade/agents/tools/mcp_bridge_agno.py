"""Agno MultiMCPTools bridge (Phase 2 Agno migration).

Replaces `agents/tools/mcp_tool_bridge.py` (which uses mcp2py + the in-house
ToolRegistry) with Agno's native `MultiMCPTools(commands=[...])` toolkit.

The 2 FastMCP stdio servers — `infrastructure/mcp/trading_mcp_server.py`
and `infrastructure/data_sources/crypto_mcp_server.py` — are unchanged;
Agno spawns them as stdio subprocesses and discovers their `listTools()`
output automatically.

Lifecycle:
    bridge = AgnoMCPBridge()
    await bridge.connect()                       # spawns both servers
    tools = bridge.toolset                       # pass to Agent(tools=[tools])
    await bridge.close()                         # call on shutdown

The bridge is a thin wrapper that hides the connect/close pair behind a
single object so callers don't need to import MultiMCPTools directly.
"""

from __future__ import annotations

import os

import structlog
from agno.tools.mcp import MultiMCPTools

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


_DEFAULT_COMMANDS: list[str] = [
    "python -m omnitrade.infrastructure.mcp.trading_mcp_server",
    "python -m omnitrade.infrastructure.data_sources.crypto_mcp_server",
]


def _subprocess_env() -> dict[str, str]:
    """Env passed to spawned MCP server subprocesses.

    Agno's `MultiMCPTools` defaults to `mcp.client.stdio.get_default_environment()`
    which returns a *sanitized* env (PATH, HOME, ...) **without** PYTHONPATH.
    Our MCP servers live inside the editable `omnitrade` package at
    `/app/src/omnitrade/...`, so the spawned `python -m omnitrade.…` command
    fails to find the module unless PYTHONPATH is forwarded explicitly.

    Forwarding the full parent env keeps DB / API-key / observability vars
    aligned with the parent process — same expectation our FastMCP servers
    had under the legacy mcp2py bridge.
    """
    return dict(os.environ)


class AgnoMCPBridge:
    """Connect-once / use-many wrapper around `agno.tools.mcp.MultiMCPTools`.

    `allow_partial_failure=True` is set so that if (e.g.) the crypto-data
    server fails to start because an upstream API key is missing, the
    trading server still works. This mirrors the legacy `mcp2py` bridge's
    soft-failure semantics.
    """

    def __init__(self, commands: list[str] | None = None, *, timeout_seconds: int = 15) -> None:
        self._commands = list(commands or _DEFAULT_COMMANDS)
        self._toolset: MultiMCPTools | None = None
        self._timeout = timeout_seconds

    @property
    def toolset(self) -> MultiMCPTools:
        if self._toolset is None:
            raise RuntimeError("AgnoMCPBridge.connect() must be awaited before .toolset")
        return self._toolset

    async def connect(self) -> MultiMCPTools:
        """Spawn the MCP server subprocesses and discover their tools."""
        if self._toolset is not None:
            return self._toolset
        toolset = MultiMCPTools(
            commands=self._commands,
            env=_subprocess_env(),
            timeout_seconds=self._timeout,
            allow_partial_failure=True,
        )
        await toolset.connect()
        self._toolset = toolset
        with_context(logger).info(
            "mcp_bridge_agno.connected",
            commands=self._commands,
        )
        return toolset

    async def close(self) -> None:
        """Gracefully shut down the MCP server subprocesses."""
        if self._toolset is None:
            return
        try:
            await self._toolset.close()
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            with_context(logger).warning(
                "mcp_bridge_agno.close_failed",
                error=str(exc),
            )
        self._toolset = None


__all__ = ["AgnoMCPBridge"]
