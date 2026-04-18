#!/usr/bin/env python3
"""G-2 gate: verify DeepSeek + LiteLLM honor ``tool_choice="required"``.

Phase 8.5b pre-merge check.

Run manually (or from CI with a secret):

  DEEPSEEK_API_KEY=sk-... uv run python scripts/verify_deepseek_tool_choice.py

Exit codes:
  0 — response has non-empty ``tool_calls`` (contract honored).
  2 — env missing (skipped). Treated as "no evidence", not a pass.
  1 — response lacked ``tool_calls`` (contract violated, merge-blocking).

The script constructs a simple prompt from the frozen ``snapshot_01`` fixture
and asks for a ``hold`` decision. The real DeepSeek API is called through
LiteLLM; **no cassette**, **no stub**. The script never commits credentials
and refuses to run without ``DEEPSEEK_API_KEY`` in the environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# apps/backend/scripts/verify_deepseek_tool_choice.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_SRC = _REPO_ROOT / "apps" / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

_FIXTURE = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "frozen"
    / "market_snapshots"
    / "case_01_swingsmith_trailing_L1.json"
)

_MODEL = "deepseek/deepseek-chat"


_HOLD_TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "hold",
            "description": "Hold the current portfolio; no new orders this cycle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Short free-text reason for holding.",
                    }
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "openPosition",
            "description": "Open a new futures position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "side": {"type": "string", "enum": ["long", "short"]},
                    "leverage": {"type": "integer"},
                    "positionSizePercent": {"type": "number"},
                },
                "required": ["symbol", "side", "leverage", "positionSizePercent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "closePosition",
            "description": "Close (fully or partially) an existing position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "percentage": {"type": "number"},
                },
                "required": ["symbol", "percentage"],
            },
        },
    },
]


def _load_snapshot() -> dict[str, Any]:
    if not _FIXTURE.exists():
        print(f"FAIL: fixture missing at {_FIXTURE}", file=sys.stderr)
        sys.exit(1)
    with _FIXTURE.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def _build_messages(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You are an autonomous trading agent. You MUST respond by calling "
        "exactly one of the provided tools (hold / openPosition / closePosition). "
        "Never reply with free-text JSON."
    )
    user = (
        "Evaluate this market snapshot and return a tool call. "
        "A cautious hold is acceptable.\n\n"
        f"{json.dumps(snapshot, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        print(
            "SKIP: DEEPSEEK_API_KEY (or LLM_API_KEY) not set; cannot verify live contract.",
            file=sys.stderr,
        )
        return 2

    # Import lazily so `--help`-like probes don't need litellm installed.
    from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient

    client = LiteLLMClient(model=_MODEL, api_key=api_key)
    snapshot = _load_snapshot()
    messages = _build_messages(snapshot)

    response = await client.complete(
        messages=messages,
        model=_MODEL,
        temperature=0.0,
        tools=_HOLD_TOOL_SCHEMA,
        tool_choice="required",
    )

    choices = response.get("choices") or []
    if not choices:
        print("FAIL: response had no choices", file=sys.stderr)
        return 1
    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        print(
            "FAIL: response lacks tool_calls — DeepSeek did not honor "
            "tool_choice='required'",
            file=sys.stderr,
        )
        print(f"  content={message.get('content')!r}", file=sys.stderr)
        return 1

    first = tool_calls[0]
    fn = (first.get("function") or {}).get("name")
    print(f"OK: DeepSeek honored tool_choice=required; first tool_call.name={fn!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
