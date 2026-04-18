"""Unit tests for MCPClient — JSON-RPC framing over a stub ASGI transport."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from omnitrade.infrastructure.mcp.client import MCPClient, MCPRPCError


def _make_transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_client_sends_well_formed_jsonrpc_request(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": "x", "result": {"value": 42}},
        )

    transport = _make_transport(handler)

    # Patch httpx.AsyncClient to use our MockTransport for this call only.
    original_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    client = MCPClient("https://mcp.example.com/rpc", headers={"x-api-key": "k"})
    result = await client.call("gas.eth", {"window": "1h"})

    assert result == {"value": 42}
    assert captured["url"] == "https://mcp.example.com/rpc"
    assert captured["headers"]["x-api-key"] == "k"
    body = captured["body"]
    assert '"jsonrpc": "2.0"' in body or '"jsonrpc":"2.0"' in body
    assert "gas.eth" in body
    assert "window" in body


@pytest.mark.asyncio
async def test_client_raises_on_rpc_error(monkeypatch: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "x",
                "error": {"code": -32602, "message": "invalid params"},
            },
        )

    transport = _make_transport(handler)
    original_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    client = MCPClient("https://mcp.example.com/rpc")
    with pytest.raises(MCPRPCError) as excinfo:
        await client.call("broken.tool")
    assert excinfo.value.code == -32602
    assert "invalid params" in excinfo.value.message


@pytest.mark.asyncio
async def test_client_list_tools(monkeypatch: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "x",
                "result": {"tools": [{"name": "a"}, {"name": "b"}, "bogus"]},
            },
        )

    transport = _make_transport(handler)
    original_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    client = MCPClient("https://mcp.example.com/rpc")
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["a", "b"]


@pytest.mark.asyncio
async def test_client_rejects_empty_endpoint() -> None:
    with pytest.raises(ValueError, match="endpoint must not be empty"):
        MCPClient("")
