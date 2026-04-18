"""Snapshot tests for the think + reflect user-message templates."""

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
        strategy_banner="策略横幅 (stable)",
        hard_risk_floor="硬风控底线 (stable)",
        tactical_box="战术盒 (stable)",
        decision_flow="决策流程 (stable)",
        market_data_block="BTC: 68500 / ETH: 3582",
        news_block="无",
        external_block="无",
        account_block="总额 1000 USDT",
        positions_block="无",
        sharpe_block="Sharpe: 1.42",
        recent_trades_block="无",
    )
    _verify_or_update(_SNAPSHOT_DIR / "think_user.snap", filled)


def test_reflect_user_template_snapshot() -> None:
    filled = REFLECT_USER_TEMPLATE.format(
        strategy_name="arena-steward",
        action="close",
        outcome_summary="盈利 +2.3%",
    )
    _verify_or_update(_SNAPSHOT_DIR / "reflect_user.snap", filled)
