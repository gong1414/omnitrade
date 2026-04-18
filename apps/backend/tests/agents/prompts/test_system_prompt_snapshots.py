"""Snapshot tests for the 2-branch system prompt.

Custom golden-file harness (per Phase 4.2 deliverable — "syrupy OR custom
golden-file"). Covers ALL 11 strategy enum values so any drift fails the
gate.

Update with:  UPDATE_PROMPT_SNAPSHOTS=1 uv run pytest tests/agents/prompts -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnitrade.agents.prompts.system import format_system_prompt
from omnitrade.domain.enums import StrategyName

_SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"

# Deterministic placeholders so snapshots are stable across machines.
_FILL_IN = {
    "strategy_desc": "【测试策略描述 — SNAPSHOT STABLE FILL】",
    "strategy_specific_content": "测试策略规则：双均线 + RSI 过滤 (SNAPSHOT STABLE FILL)",
    "risk_tolerance": "每笔风险 ≤ 1% 账户净值 (SNAPSHOT STABLE FILL)",
}


def _snapshot_path(strategy: StrategyName) -> Path:
    return _SNAPSHOT_DIR / f"system_prompt__{strategy.value}.snap"


@pytest.mark.parametrize(
    "strategy",
    list(StrategyName),
    ids=[s.value for s in StrategyName],
)
def test_system_prompt_snapshot(strategy: StrategyName) -> None:
    """Every StrategyName value is covered — gate fails if any enum is missing."""
    rendered = format_system_prompt(
        strategy,
        strategy_desc=_FILL_IN["strategy_desc"],
        strategy_specific_content=_FILL_IN["strategy_specific_content"],
        risk_tolerance=_FILL_IN["risk_tolerance"],
    )
    path = _snapshot_path(strategy)

    if os.environ.get("UPDATE_PROMPT_SNAPSHOTS") == "1":
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return

    assert path.exists(), (
        f"Missing snapshot for {strategy.value} at {path}; "
        f"re-run with UPDATE_PROMPT_SNAPSHOTS=1 to create it."
    )
    expected = path.read_text(encoding="utf-8")
    assert rendered == expected, (
        f"System prompt drift for strategy={strategy.value}. "
        f"Re-run with UPDATE_PROMPT_SNAPSHOTS=1 after reviewing."
    )


def test_11_strategies_have_snapshots() -> None:
    """Hard gate: all 11 StrategyName enum values must have a snapshot file."""
    all_strategies = list(StrategyName)
    assert len(all_strategies) == 11, f"StrategyName has {len(all_strategies)} members, expected 11"
    missing = [s.value for s in all_strategies if not _snapshot_path(s).exists()]
    assert missing == [], f"missing snapshot files for: {missing}"


def test_minimal_branch_applies_only_to_two_strategies() -> None:
    """AI_AUTONOMOUS and ALPHA_BETA are the only minimal-branch strategies."""
    minimal_markers = []
    full_markers = []
    for s in StrategyName:
        text = format_system_prompt(
            s,
            strategy_desc=_FILL_IN["strategy_desc"],
            strategy_specific_content=_FILL_IN["strategy_specific_content"],
            risk_tolerance=_FILL_IN["risk_tolerance"],
        )
        if "完全自主的AI加密货币交易员" in text:
            minimal_markers.append(s)
        if "世界顶级的专业量化交易员" in text:
            full_markers.append(s)

    assert set(minimal_markers) == {StrategyName.AI_AUTONOMOUS, StrategyName.ALPHA_BETA}
    assert len(full_markers) == 9
    # Mutual exclusivity: no strategy matches both markers.
    assert not (set(minimal_markers) & set(full_markers))
