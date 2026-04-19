"""User-message template for the reflect step.

The reflect step summarises trade outcomes and extracts a lesson to be
appended to the vector-store RAG. Kept intentionally small -- the LangGraph
think node does the heavy lifting; reflection is a post-step summariser.

PR-B2 Phase B rewrote this template into English and made the output
contract more structured (lessons_learned + adjustment_plan) so the
downstream RAG ingester has stable field names.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

REFLECT_USER_TEMPLATE = """\
[CYCLE POST-MORTEM]

Strategy: {strategy_name}
Action taken: {action}
Outcome: {outcome_summary}

Answer tersely, grounded on numeric evidence from the cycle:
1. Was the decision correct given the evidence available at entry? Why or why not?
2. Extract ONE reusable lesson (``lessons_learned``) and ONE concrete adjustment for the next identical setup (``adjustment_plan``). Keep each under 240 characters.
3. Return a single JSON object with NO markdown fencing:
{{"lessons_learned": "...", "adjustment_plan": "...", "confidence": 0.0-1.0, "tags": ["..."]}}
"""

reflect_user_template: HumanMessagePromptTemplate = HumanMessagePromptTemplate.from_template(
    REFLECT_USER_TEMPLATE
)


def build_reflect_prompt() -> ChatPromptTemplate:
    """Return a ``ChatPromptTemplate`` with only the user reflect message."""
    return ChatPromptTemplate.from_messages([reflect_user_template])


__all__ = ["REFLECT_USER_TEMPLATE", "build_reflect_prompt", "reflect_user_template"]
