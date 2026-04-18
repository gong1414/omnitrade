"""Helpers to synthesise vcrpy cassettes from the hand-curated decision contracts.

The 22 frozen fixtures are hand-authored contracts — tool calls, state
writes, close-path — one per close-path scenario. For behavioural-
equivalence replay we need a *deterministic LLM response* per fixture
that, when parsed by ``agents/think_node._decision_from_llm_response``,
yields a Decision matching the fixture's expected action.

This module turns each ``baseline_decisions/case_NN_*.json`` into a
cassette YAML that ships with the repo. It is pure — no network, no
side-effects beyond the cassette files that live in ``cassettes/``.

Monitor-initiated close paths (``trailing_stop`` / ``stop_loss`` /
``partial_profit``) have no LLM call in production; the think-node is
only consulted on ``ai_decision`` / ``none`` close paths. For those
monitor paths we still record a cassette with ``hold`` so the gate
can exercise the non-think path uniformly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CASSETTE_DIR: Path = Path(__file__).parent / "cassettes"
# apps/backend/tests/behavioral_equivalence/_cassette_synth.py  ->  repo root
_REPO_ROOT = Path(__file__).parents[4]
FIXTURES_DIR: Path = _REPO_ROOT / "tests" / "fixtures" / "frozen" / "baseline_decisions"


def _pick_ai_tool_call(fixture: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the single (tool_name, args) pair that represents the decision.

    Preference order:
      1. First tool-call with ``initiated_by == "ai"``.
      2. If none exists (monitor-only fixtures), fall back to ``("hold", {})``.
    This mirrors the think-node contract: monitor-triggered closes are
    handled OUTSIDE the LLM loop, so the LLM response is a benign hold.
    """
    for call in fixture.get("tool_calls") or []:
        if call.get("initiated_by") == "ai":
            tool_name = call.get("tool") or "hold"
            args = dict(call.get("args") or {})
            return tool_name, args
    return "hold", {}


def _tool_name_to_openai(tool_name: str) -> str:
    """Map frozen-fixture tool name → the OpenAI-tool name the think node parses.

    The agent exposes three primitive tool names; jury sub-agents map to
    ``hold`` because they don't change state on their own — only the final
    judge's ``closePosition`` or ``openPosition`` drives a decision.
    """
    passthrough = {"openPosition", "closePosition", "partialClose", "hold"}
    if tool_name in passthrough:
        return tool_name
    # Non-decision tools (technicalAnalyst / trendAnalyst / riskAssessor,
    # monitor events, etc.) fold into ``hold`` — see module docstring.
    return "hold"


def _build_openai_response(fixture_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Assemble an OpenAI-style chat-completion response with one tool call."""
    mapped = _tool_name_to_openai(tool_name)
    if mapped == "hold":
        return {
            "id": f"chatcmpl-{fixture_id}",
            "object": "chat.completion",
            "model": "deepseek-chat",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call-{fixture_id}",
                                "type": "function",
                                "function": {
                                    "name": "hold",
                                    "arguments": json.dumps({"reason": "no_signal"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
    return {
        "id": f"chatcmpl-{fixture_id}",
        "object": "chat.completion",
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call-{fixture_id}",
                            "type": "function",
                            "function": {
                                "name": mapped,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _serialize_cassette(response_body: dict[str, Any]) -> str:
    """Return a minimal but valid vcrpy cassette YAML string."""
    body_json = json.dumps(response_body)
    # Escape single quotes inside the body for YAML single-quoted scalar.
    body_escaped = body_json.replace("'", "''")
    return (
        "interactions:\n"
        "- request:\n"
        "    method: POST\n"
        "    uri: https://fixtures.omnitrade.test/v1/chat/completions\n"
        "    body: '{}'\n"
        "    headers:\n"
        "      content-type:\n"
        "      - application/json\n"
        "  response:\n"
        "    status:\n"
        "      code: 200\n"
        "      message: OK\n"
        "    headers:\n"
        "      content-type:\n"
        "      - application/json\n"
        "    body:\n"
        f"      string: '{body_escaped}'\n"
        "version: 1\n"
    )


def load_baseline_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"baseline fixture is not an object: {path}")
    return data


def generate_cassette_for_fixture(fixture_path: Path) -> Path:
    """Write ``<cassettes>/<case_id>.yaml`` and return its path."""
    fixture = load_baseline_fixture(fixture_path)
    case_id = str(fixture.get("case_id") or fixture_path.stem)
    tool_name, args = _pick_ai_tool_call(fixture)
    response = _build_openai_response(case_id, tool_name, args)
    yaml_text = _serialize_cassette(response)
    CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
    out = CASSETTE_DIR / f"{case_id}.yaml"
    out.write_text(yaml_text, encoding="utf-8")
    return out


def generate_all_cassettes() -> list[Path]:
    """Generate one cassette per baseline_decisions/*.json. Return all paths."""
    if not FIXTURES_DIR.exists():
        raise FileNotFoundError(f"baseline_decisions dir missing: {FIXTURES_DIR}")
    written: list[Path] = []
    for fixture_path in sorted(FIXTURES_DIR.glob("case_*.json")):
        written.append(generate_cassette_for_fixture(fixture_path))
    return written


__all__ = [
    "CASSETTE_DIR",
    "FIXTURES_DIR",
    "generate_all_cassettes",
    "generate_cassette_for_fixture",
    "load_baseline_fixture",
]
