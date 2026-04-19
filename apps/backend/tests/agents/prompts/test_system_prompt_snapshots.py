"""Snapshot tests for the 2-branch system prompt.

Custom golden-file harness (per Phase 4.2 deliverable — "syrupy OR custom
golden-file"). Covers ALL 11 strategy enum values so any drift fails the
gate.

PR-B2 Phase B (2026-04-19) rewrote every production prompt into the
Alpha Arena 4-section English structure. The CJK-absence assertion below
is the permanent guard-rail: any future prompt that reintroduces Chinese
literal text will fail the gate.

Update with:  UPDATE_PROMPT_SNAPSHOTS=1 uv run pytest tests/agents/prompts -v
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from omnitrade.agents.prompts.multi_agent import (
    MONEY_FLOW_EXPERT_PROMPT,
    PREDICTION_EXPERT_PROMPT,
    RISK_ASSESSOR_PROMPT,
    RISK_CONTROL_EXPERT_PROMPT,
    TECHNICAL_ANALYST_PROMPT,
    TREND_ANALYST_PROMPT,
    TREND_EXPERT_PROMPT,
)
from omnitrade.agents.prompts.reflect import REFLECT_USER_TEMPLATE
from omnitrade.agents.prompts.system import format_system_prompt
from omnitrade.agents.prompts.think import THINK_USER_TEMPLATE
from omnitrade.domain.enums import StrategyName

_SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"

# Deterministic placeholders so snapshots are stable across machines.
_FILL_IN = {
    "strategy_desc": "Strategy description (SNAPSHOT STABLE FILL)",
    "strategy_specific_content": (
        "Strategy rules: dual-EMA crossover + RSI filter (SNAPSHOT STABLE FILL)"
    ),
    "risk_tolerance": "<=1% account equity per trade (SNAPSHOT STABLE FILL)",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


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
    minimal_markers: list[StrategyName] = []
    full_markers: list[StrategyName] = []
    for s in StrategyName:
        text = format_system_prompt(
            s,
            strategy_desc=_FILL_IN["strategy_desc"],
            strategy_specific_content=_FILL_IN["strategy_specific_content"],
            risk_tolerance=_FILL_IN["risk_tolerance"],
        )
        # Minimal branch has the "autonomous crypto-futures trading system"
        # identity (no strategy_name interpolation); full branch names the
        # strategy explicitly. Both markers are unique to their branch.
        if "SYSTEM HARD RISK FLOOR" in text:
            minimal_markers.append(s)
        if "world-class systematic quantitative trader" in text:
            full_markers.append(s)

    assert set(minimal_markers) == {StrategyName.AI_AUTONOMOUS, StrategyName.ALPHA_BETA}
    assert len(full_markers) == 9
    # Mutual exclusivity: no strategy matches both markers.
    assert not (set(minimal_markers) & set(full_markers))


# ── CJK-absence guard rails (PR-B2 Phase B) ───────────────────────────────


@pytest.mark.parametrize(
    "strategy",
    list(StrategyName),
    ids=[s.value for s in StrategyName],
)
def test_system_prompt_contains_no_cjk(strategy: StrategyName) -> None:
    """Every system prompt MUST be pure English (reasoning language is
    controlled by the runtime ``output_language`` surfaced through
    StructuredReason, NOT by the system prompt itself).
    """
    rendered = format_system_prompt(
        strategy,
        strategy_desc=_FILL_IN["strategy_desc"],
        strategy_specific_content=_FILL_IN["strategy_specific_content"],
        risk_tolerance=_FILL_IN["risk_tolerance"],
    )
    match = _CJK_RE.search(rendered)
    assert match is None, (
        f"CJK character {match.group()!r} leaked into system prompt for "
        f"strategy={strategy.value} at index {match.start() if match else '-'}."
    )


def test_think_template_contains_no_cjk() -> None:
    """The think user-template is a raw string (no format call needed for CJK scan)."""
    match = _CJK_RE.search(THINK_USER_TEMPLATE)
    assert match is None, (
        f"CJK character {match.group()!r} leaked into THINK_USER_TEMPLATE "
        f"at index {match.start() if match else '-'}."
    )


def test_reflect_template_contains_no_cjk() -> None:
    """Reflect user-template must also stay English-only."""
    match = _CJK_RE.search(REFLECT_USER_TEMPLATE)
    assert match is None, (
        f"CJK character {match.group()!r} leaked into REFLECT_USER_TEMPLATE "
        f"at index {match.start() if match else '-'}."
    )


@pytest.mark.parametrize(
    "name,prompt",
    [
        ("trend_expert", TREND_EXPERT_PROMPT),
        ("prediction_expert", PREDICTION_EXPERT_PROMPT),
        ("money_flow_expert", MONEY_FLOW_EXPERT_PROMPT),
        ("risk_control_expert", RISK_CONTROL_EXPERT_PROMPT),
        ("technical_analyst", TECHNICAL_ANALYST_PROMPT),
        ("trend_analyst", TREND_ANALYST_PROMPT),
        ("risk_assessor", RISK_ASSESSOR_PROMPT),
    ],
)
def test_multi_agent_prompt_contains_no_cjk(name: str, prompt: str) -> None:
    """All 4 squad experts + 3 tribunal jurors must stay English-only."""
    match = _CJK_RE.search(prompt)
    assert match is None, (
        f"CJK character {match.group()!r} leaked into {name} prompt "
        f"at index {match.start() if match else '-'}."
    )
