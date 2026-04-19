"""Snapshot tests for the think + reflect user-message templates.

PR-B2 Phase B added the ``{output_language}`` placeholder to the think
template trailer so the model can render its reasoning in the caller's
configured language while keeping the system prompt English-only.
"""

from __future__ import annotations

import os
from pathlib import Path

from omnitrade.agents.prompts.reflect import REFLECT_USER_TEMPLATE
from omnitrade.agents.prompts.think import THINK_USER_TEMPLATE

_SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"


def _verify_or_update(path: Path, rendered: str) -> None:
    if os.environ.get("UPDATE_PROMPT_SNAPSHOTS") == "1":
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    assert path.exists(), f"missing snapshot: {path}"
    assert path.read_text(encoding="utf-8") == rendered, (
        f"snapshot drift at {path} — re-run with UPDATE_PROMPT_SNAPSHOTS=1."
    )


def test_think_user_template_snapshot() -> None:
    filled = THINK_USER_TEMPLATE.format(
        iteration=42,
        current_time="2026-04-17 10:00",
        minutes_elapsed=20,
        interval_minutes=20,
        strategy_banner="Strategy banner (stable)",
        hard_risk_floor="Hard risk floor (stable)",
        tactical_box="Tactical box (stable)",
        decision_flow="Decision flow (stable)",
        market_data_block="BTC: 68500 / ETH: 3582",
        news_block="none",
        external_block="none",
        account_block="Equity 1000 USDT",
        positions_block="none",
        sharpe_block="Sharpe: 1.42",
        recent_trades_block="none",
        output_language="zh",
    )
    _verify_or_update(_SNAPSHOT_DIR / "think_user.snap", filled)


def test_reflect_user_template_snapshot() -> None:
    filled = REFLECT_USER_TEMPLATE.format(
        strategy_name="arena-steward",
        action="close",
        outcome_summary="realized PnL +2.3%",
    )
    _verify_or_update(_SNAPSHOT_DIR / "reflect_user.snap", filled)


def test_think_template_has_output_language_placeholder() -> None:
    """The anti-hold v1 trailer must reference ``{output_language}``."""
    assert "{output_language}" in THINK_USER_TEMPLATE


def test_think_template_has_tool_enumeration_trailer() -> None:
    """Every think invocation must remind the LLM of the 4 tool names
    (open_position / close_position / partial_close / hold_tool) so the
    action-forced framing from Phase A survives into production."""
    for tool_name in (
        "open_position",
        "close_position",
        "partial_close",
        "hold_tool",
    ):
        assert tool_name in THINK_USER_TEMPLATE, f"missing tool name: {tool_name}"


def test_reflect_template_has_structured_json_contract() -> None:
    """Reflect output must land in a single JSON object with the
    lessons_learned + adjustment_plan fields the RAG ingester expects."""
    assert "lessons_learned" in REFLECT_USER_TEMPLATE
    assert "adjustment_plan" in REFLECT_USER_TEMPLATE
