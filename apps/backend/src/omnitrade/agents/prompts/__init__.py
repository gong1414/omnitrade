"""Prompt templates for the Agno trading agent.

Two system prompt branches:
  * Minimal prompt — strategies ``arena-autopilot`` / ``arena-dual-signal``
  * Full "World-class Trader" prompt — the other 9 strategies

Snapshot tests under ``tests/agents/prompts/__snapshots__`` lock drift.
"""

from omnitrade.agents.prompts.reflect import REFLECT_USER_TEMPLATE
from omnitrade.agents.prompts.system import (
    FULL_SYSTEM_PROMPT_TEMPLATE,
    MINIMAL_SYSTEM_PROMPT_TEMPLATE,
    format_system_prompt,
)
from omnitrade.agents.prompts.think import THINK_USER_TEMPLATE

__all__ = [
    "FULL_SYSTEM_PROMPT_TEMPLATE",
    "MINIMAL_SYSTEM_PROMPT_TEMPLATE",
    "REFLECT_USER_TEMPLATE",
    "THINK_USER_TEMPLATE",
    "format_system_prompt",
]
