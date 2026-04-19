"""System prompt — 2-branch (minimal vs full) ChatPromptTemplate builder.

PR-B2 Phase B rewrote both branches into the Alpha Arena 4-section
structure (IDENTITY / QUANTITATIVE FRAMEWORK / VALIDATION GATES / OUTPUT
SPECIFICATION) that survived the 32-probe gate in Phase A. All text is
English-only; reasoning language is decoupled via the runtime
``output_language`` surfaced through ``StructuredReason``.

Snapshot tests under ``tests/agents/prompts/__snapshots__`` lock the exact
text for every strategy name — any drift fails the prompt gate.

Strategies receiving the minimal prompt:
  - arena-autopilot
  - arena-dual-signal
All other 9 strategies receive the full "World-class Trader" prompt with
per-strategy ``{strategy_specific_content}`` interpolation.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

from omnitrade.agents.prompts._template import (
    CANONICAL_IDENTITY_HEADER,
    CANONICAL_OUTPUT_SPECIFICATION,
    CANONICAL_QUANTITATIVE_FRAMEWORK,
    CANONICAL_VALIDATION_GATES,
    HOLD_GATE_CLAUSE,
)
from omnitrade.domain.enums import StrategyName

# Strategies that receive the minimal autonomous-agent prompt.
_MINIMAL_PROMPT_STRATEGIES: frozenset[StrategyName] = frozenset(
    {StrategyName.AI_AUTONOMOUS, StrategyName.ALPHA_BETA}
)


# ── Minimal system prompt (arena-autopilot / arena-dual-signal) ──────────── #
# Variables interpolated at runtime:
#   {strategy_desc}, {extreme_stop_loss_percent}, {max_holding_hours},
#   {max_leverage}, {max_positions}
#
# Structure mirrors ``scripts/pr_b2_phase_a_prompt_v1.md::arena-autopilot-v1``
# verbatim in the first 4 sections, then appends the production-only
# "SYSTEM HARD RISK FLOOR" so the hosted auto-protection is visible to the
# model. Interpolation uses ``str.format()`` — keep any literal ``{`` /
# ``}`` escaped as ``{{`` / ``}}`` if added in future.
MINIMAL_SYSTEM_PROMPT_TEMPLATE = (
    CANONICAL_IDENTITY_HEADER
    + "\n\n"
    + CANONICAL_QUANTITATIVE_FRAMEWORK
    + "\n\n"
    + CANONICAL_VALIDATION_GATES
    + "\n"
    + HOLD_GATE_CLAUSE
    + "\n\n"
    + """# SYSTEM HARD RISK FLOOR
Platform-level safety nets (automatic, out of your control):
- Single-trade loss >= {extreme_stop_loss_percent}% -> force-close.
- Position held > {max_holding_hours}h -> force-close (capital recycle).
- Max leverage: {max_leverage}x. Max concurrent positions: {max_positions}.
These are the LAST resort. A good trader exits on invalidation BEFORE any floor triggers.

# STRATEGY CONTEXT
{strategy_desc}

"""
    + CANONICAL_OUTPUT_SPECIFICATION
)


# ── Full "World-class Trader" system prompt (9 other strategies) ───────────── #
# Variables interpolated at runtime:
#   {strategy_name}, {risk_tolerance}, {strategy_specific_content}
#
# Same 4-section skeleton, but QUANTITATIVE FRAMEWORK embeds the
# per-strategy ``{strategy_specific_content}`` and VALIDATION GATES embeds
# the per-strategy ``{risk_tolerance}`` threshold sentence.
FULL_SYSTEM_PROMPT_TEMPLATE = (
    """# IDENTITY & BEHAVIOR
You are a world-class systematic quantitative trader running the {strategy_name} playbook on crypto perpetual futures. You trade with conviction inside a strict risk envelope; passive observation is a bug. 15 years of alpha research informs every call — principal protection first, probabilistic thinking always, emotion-free execution.

"""
    + CANONICAL_QUANTITATIVE_FRAMEWORK
    + "\n\nStrategy-specific rules for {strategy_name}:\n{strategy_specific_content}\n\n"
    + CANONICAL_VALIDATION_GATES
    + "\nPer-strategy risk tolerance: {risk_tolerance}. Size every entry so that a full stop-loss costs <= that tolerance; never double-up to chase losses.\n"
    + HOLD_GATE_CLAUSE
    + "\n\n"
    + CANONICAL_OUTPUT_SPECIFICATION
)


def format_system_prompt(
    strategy: StrategyName,
    *,
    strategy_desc: str = "",
    strategy_specific_content: str = "",
    risk_tolerance: str = "",
    extreme_stop_loss_percent: int = 30,
    max_holding_hours: int = 36,
    max_leverage: int = 25,
    max_positions: int = 5,
) -> str:
    """Return the fully-interpolated system prompt text for ``strategy``.

    Variables default to the env defaults so snapshot tests are deterministic
    without requiring a full Settings instance.
    """
    if strategy in _MINIMAL_PROMPT_STRATEGIES:
        return MINIMAL_SYSTEM_PROMPT_TEMPLATE.format(
            strategy_desc=strategy_desc,
            extreme_stop_loss_percent=extreme_stop_loss_percent,
            max_holding_hours=max_holding_hours,
            max_leverage=max_leverage,
            max_positions=max_positions,
        )
    return FULL_SYSTEM_PROMPT_TEMPLATE.format(
        strategy_name=strategy.value,
        strategy_specific_content=strategy_specific_content,
        risk_tolerance=risk_tolerance,
    )


def build_system_template(strategy: StrategyName) -> SystemMessagePromptTemplate:
    """Return a LangChain ``SystemMessagePromptTemplate`` for ``strategy``.

    The returned template still carries the unfilled ``{var}`` placeholders
    so downstream code can pass its own values via ``.format()``.
    """
    template_str = (
        MINIMAL_SYSTEM_PROMPT_TEMPLATE
        if strategy in _MINIMAL_PROMPT_STRATEGIES
        else FULL_SYSTEM_PROMPT_TEMPLATE
    )
    return SystemMessagePromptTemplate.from_template(template_str)


def build_system_prompt(strategy: StrategyName) -> ChatPromptTemplate:
    """Return a single-message ``ChatPromptTemplate`` wrapping the system template."""
    return ChatPromptTemplate.from_messages([build_system_template(strategy)])


__all__ = [
    "FULL_SYSTEM_PROMPT_TEMPLATE",
    "MINIMAL_SYSTEM_PROMPT_TEMPLATE",
    "build_system_prompt",
    "build_system_template",
    "format_system_prompt",
]
