"""User-message template for the reflect step.

The reflect step summarises trade outcomes and extracts a lesson to be
appended to the vector-store RAG. Kept intentionally small — the LangGraph
think node does the heavy lifting; reflection is a post-step summariser.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

REFLECT_USER_TEMPLATE = """\
【本周期交易复盘】

策略：{strategy_name}
动作：{action}
结果：{outcome_summary}

请回答：
1. 本周期决策是否合理？为什么？
2. 可以提炼成什么可复用的经验（lesson）？
3. 请以 JSON 返回 {{"lesson": "...", "confidence": 0-1, "tags": ["..."]}}
"""

reflect_user_template: HumanMessagePromptTemplate = HumanMessagePromptTemplate.from_template(
    REFLECT_USER_TEMPLATE
)


def build_reflect_prompt() -> ChatPromptTemplate:
    """Return a ``ChatPromptTemplate`` with only the user reflect message."""
    return ChatPromptTemplate.from_messages([reflect_user_template])


__all__ = ["REFLECT_USER_TEMPLATE", "build_reflect_prompt", "reflect_user_template"]
