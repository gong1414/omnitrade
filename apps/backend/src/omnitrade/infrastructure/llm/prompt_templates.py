"""Prompt template builders for the AI trading agent.

Two system prompt branches:
  1. Minimal prompt — strategies: arena-autopilot, arena-dual-signal
  2. Full "World-class Trader" prompt — the other 9 strategies

Snapshot tests under ``tests/agents/prompts/__snapshots__`` lock the exact
text for every strategy name — any drift fails the prompt gate.
"""

from __future__ import annotations

from typing import Literal

from omnitrade.domain.enums import StrategyName

# Strategies that get the minimal autonomous-agent prompt
_MINIMAL_PROMPT_STRATEGIES: frozenset[StrategyName] = frozenset(
    {StrategyName.AI_AUTONOMOUS, StrategyName.ALPHA_BETA}
)

# ── Minimal system prompt (arena-autopilot / arena-dual-signal) ─────────────────────
MINIMAL_SYSTEM_PROMPT = """\
You are an autonomous AI trading agent managing a cryptocurrency futures portfolio.

Your goal is to maximize risk-adjusted returns while strictly controlling drawdown.

You have access to real-time market data, technical indicators, account information,
and historical trading lessons. Use all available tools to make informed decisions.

Key constraints:
- Never exceed the configured maximum leverage
- Respect the maximum position count limit
- Apply strict stop-loss discipline
- Log every decision with clear reasoning

Return a structured JSON decision with: action, symbol, side, size, leverage, reasoning.
"""

# ── Full "World-class Trader" system prompt (all other 9 strategies) ───────
FULL_SYSTEM_PROMPT = """\
You are a world-class cryptocurrency futures trader with deep expertise in:
- Technical analysis (EMA, MACD, RSI, ATR, Bollinger Bands)
- Market microstructure (order book, funding rates, open interest)
- Risk management (position sizing, stop-loss, drawdown control)
- Sentiment analysis (fear/greed index, on-chain metrics, news flow)
- Multi-timeframe analysis

Your mission: manage a futures portfolio to achieve consistent risk-adjusted returns.

## Trading Philosophy
1. Capital preservation above all — never risk more than configured drawdown limits
2. High-conviction trades only — entry when multiple signals align
3. Dynamic position management — trail stops, take partial profits at milestones
4. Learn from every trade — extract lessons and apply to future decisions

## Decision Framework
1. OBSERVE: Gather market data, signals, news, account state
2. ANALYZE: Apply technical + fundamental + sentiment analysis
3. DECIDE: If conviction > threshold, choose action; otherwise HOLD
4. MANAGE: Monitor existing positions for stop/trail/partial-profit triggers
5. REFLECT: Record outcome and extract learning

## Risk Rules (NON-NEGOTIABLE)
- Hard stop-loss at extreme_stop_loss_percent (e.g. -30%)
- Drawdown warning at account_drawdown_warning_percent
- No new positions when drawdown > account_drawdown_no_new_position_percent
- Force-close all positions when drawdown > account_drawdown_force_close_percent
- Maximum positions: max_positions
- Maximum leverage: max_leverage

## Output Format
Return a structured JSON decision:
{
  "action": "open|close|partial_close|hold",
  "symbol": "BTC_USDT",
  "side": "long|short",
  "size": <decimal>,
  "leverage": <integer>,
  "stop_loss": <decimal or null>,
  "take_profit": <decimal or null>,
  "confidence": <0.0-1.0>,
  "reasoning": "<clear explanation>",
  "lessons_applied": ["<lesson_id>"]
}
"""


def format_system_prompt(strategy: StrategyName) -> str:
    """Return the correct system prompt for the given strategy.

    Strategies arena-autopilot and arena-dual-signal receive a minimal prompt;
    the other 9 strategies receive the full World-class Trader prompt.
    """
    if strategy in _MINIMAL_PROMPT_STRATEGIES:
        return MINIMAL_SYSTEM_PROMPT
    return FULL_SYSTEM_PROMPT


def tool_choice_for_strategy(
    strategy: StrategyName,
) -> Literal["auto", "required", "none"] | None:
    """Return the LiteLLM ``tool_choice`` policy for a given strategy.

    Phase 8.5b: the minimal-prompt branch (``arena-autopilot`` / ``arena-dual-signal``)
    must force ``tool_choice="required"`` so that DeepSeek + LiteLLM cannot
    silently fall back to content-JSON; the strict ``_decision_from_llm_response``
    path otherwise raises :class:`ToolCallRequiredError`. Full-prompt strategies
    return ``None`` to preserve pre-8.5b byte-exact behavior for cassette
    replay (characterization gate).
    """
    if strategy in _MINIMAL_PROMPT_STRATEGIES:
        return "required"
    return None


def build_messages(
    strategy: StrategyName,
    user_content: str,
) -> list[dict[str, str]]:
    """Build a messages list ready for LLMClient.complete().

    Args:
        strategy: The active trading strategy (determines system prompt branch).
        user_content: The user-turn content (market snapshot JSON, etc.).

    Returns:
        List of {"role": ..., "content": ...} dicts.
    """
    return [
        {"role": "system", "content": format_system_prompt(strategy)},
        {"role": "user", "content": user_content},
    ]
