"""Unit tests for MCPRegistry — dynamic loading + lookup semantics."""

from __future__ import annotations

import pytest

from omnitrade.infrastructure.mcp.registry import MCPRegistry


def test_register_and_lookup() -> None:
    reg = MCPRegistry()
    reg.register(
        "gas.eth",
        "https://mcp.example.com/rpc",
        description="eth gas",
    )
    assert reg.has("gas.eth")
    assert reg.names() == ["gas.eth"]
    desc = reg.descriptor("gas.eth")
    assert desc["endpoint"] == "https://mcp.example.com/rpc"
    assert desc["description"] == "eth gas"


def test_load_from_config_skips_incomplete_and_non_dict() -> None:
    reg = MCPRegistry()
    reg.load_from_config(
        [
            {"name": "good", "endpoint": "https://x/y", "description": "ok"},
            {"name": "no-endpoint"},  # missing endpoint -> skipped
            "not-a-dict",  # type: ignore[list-item]
            {
                "name": "with-timeout",
                "endpoint": "https://z/q",
                "timeout": 5.0,
            },
        ]
    )
    assert reg.names() == ["good", "with-timeout"]


def test_register_rejects_empty_name() -> None:
    reg = MCPRegistry()
    with pytest.raises(ValueError, match="name must not be empty"):
        reg.register("", "https://x/y")


def test_descriptor_keyerror_for_unknown_tool() -> None:
    reg = MCPRegistry()
    with pytest.raises(KeyError):
        reg.descriptor("missing")


@pytest.mark.asyncio
async def test_call_keyerror_for_unknown_tool() -> None:
    reg = MCPRegistry()
    with pytest.raises(KeyError):
        await reg.call("missing", {})
