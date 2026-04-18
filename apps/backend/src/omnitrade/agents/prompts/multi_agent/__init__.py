"""Multi-agent sub-agent prompt templates (Phase 8.5a).

Seven ``SYSTEM_PROMPT`` constants — 4 arena-raider-squad experts + 3
arena-tribunal jurors. Each prompt is a short role preamble
plus a JSON output contract (``verdict``/``confidence``/``reasoning``).
"""

from omnitrade.agents.prompts.multi_agent.money_flow_expert import (
    SYSTEM_PROMPT as MONEY_FLOW_EXPERT_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.prediction_expert import (
    SYSTEM_PROMPT as PREDICTION_EXPERT_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.risk_assessor import (
    SYSTEM_PROMPT as RISK_ASSESSOR_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.risk_control_expert import (
    SYSTEM_PROMPT as RISK_CONTROL_EXPERT_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.technical_analyst import (
    SYSTEM_PROMPT as TECHNICAL_ANALYST_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.trend_analyst import (
    SYSTEM_PROMPT as TREND_ANALYST_PROMPT,
)
from omnitrade.agents.prompts.multi_agent.trend_expert import (
    SYSTEM_PROMPT as TREND_EXPERT_PROMPT,
)

__all__ = [
    "MONEY_FLOW_EXPERT_PROMPT",
    "PREDICTION_EXPERT_PROMPT",
    "RISK_ASSESSOR_PROMPT",
    "RISK_CONTROL_EXPERT_PROMPT",
    "TECHNICAL_ANALYST_PROMPT",
    "TREND_ANALYST_PROMPT",
    "TREND_EXPERT_PROMPT",
]
