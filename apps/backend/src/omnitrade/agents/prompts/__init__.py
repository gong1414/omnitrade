"""ChatPromptTemplate-based prompt authoring.

Two system prompt branches:
  * Minimal prompt — strategies ``arena-autopilot`` / ``arena-dual-signal``
  * Full "World-class Trader" prompt — the other 9 strategies

Snapshot tests under ``tests/agents/prompts/__snapshots__`` lock drift.
"""

from omnitrade.agents.prompts.reflect import build_reflect_prompt, reflect_user_template
from omnitrade.agents.prompts.system import build_system_prompt, build_system_template
from omnitrade.agents.prompts.think import build_think_prompt, think_user_template

__all__ = [
    "build_reflect_prompt",
    "build_system_prompt",
    "build_system_template",
    "build_think_prompt",
    "reflect_user_template",
    "think_user_template",
]
