"""StructuredReason — production schema module for Step 1 of Phase 2 rewrite.

This module defines the immutable JSON contract that:
  - Prompts describe (the LLM must emit a conforming ``reason`` object).
  - Tools validate (each tool arg spec embeds ``STRUCTURED_REASON_JSON_SCHEMA``).
  - The DB persists (Step 2 alembic migration uses the column list at the bottom of
    this file as its authoritative source of truth).

**Design ancestry / prompt-structure sources**:
  - Alpha Arena prompt pattern (kojott/LLM-trader-test, MIT licence):
    ``market_context / gates_passed / invalidation_condition / plan / confidence``
    field names were stabilised in the project's Step 0 live DeepSeek V3.2 probe
    (see ``.omc/autopilot/step-0-report.md`` §2 — 20/20 probes round-tripped without
    schema drift).  For PR-B2 prompt authors: the gate-entry wording convention
    ("EMA alignment gate: <evidence>") originates in kojott/LLM-trader-test
    ``strategies/arena_autopilot.py::SYSTEM_PROMPT`` — keep that sentence-level
    structure when writing ``VALIDATION GATES`` sections so the model learns to
    populate ``gates_passed`` with matching phrasing.
  - SnowingFox/open-nof1.ai ``think_node`` structured-output approach: the
    ``justification`` field mirrors the ``reasoning_summary`` block in that project's
    CoT design.  Step 0 observed DeepSeek V3.2 produces 1 000 - 1 700-char
    justifications unprompted (mean ≈ 1 385 chars), far above the 200-char floor.
  - ``output_language`` is a Step 1 addition driven by the ``OUTPUT_LANGUAGE`` env var
    (default ``"zh"``); see ``config.py`` and ``.env.example``.  Step 0 intentionally
    stayed on the minimal preview schema without this field; Step 1 adds it and a
    re-probe is expected before PR-B2 merge.

**PR-B1 constraints** (do NOT violate):
  - This module does NOT import ``build_hold_tool`` (hold remains a parser branch in
    PR-B1; ``build_hold_tool`` ships in PR-B2).
  - This module does NOT alter existing tool schema integration (``trade_execution.py``
    is untouched in PR-B1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanBlock(BaseModel):
    """Optional numeric trade plan.

    All fields are ``Optional`` because ``hold`` decisions carry ``plan=None`` —
    there is no entry / SL / TP for a no-action cycle.  The LLM is NOT penalised
    for omitting ``take_profit_2`` on single-target trades (Step 0 showed DeepSeek
    V3.2 sets it to ``null`` roughly 60% of the time, which is semantically correct).

    Fields ``risk_usd`` and ``r_multiple_target`` are kept because the model reliably
    computes them from ``(entry - stop_loss) * size``, providing a free sanity-check
    column for downstream validators (Step 0 - all 8 open-position probes populated
    these with numerically consistent values).
    """

    entry: float | None = Field(
        default=None,
        description=(
            "Planned entry price for the trade.  Must be non-zero for open_position "
            "and partial_close decisions; null for hold."
        ),
    )
    stop_loss: float | None = Field(
        default=None,
        description=(
            "Stop-loss price level below (long) or above (short) the entry.  "
            "Non-zero for actionable decisions; null for hold."
        ),
    )
    take_profit_1: float | None = Field(
        default=None,
        description=(
            "First take-profit price target.  Required for open_position; "
            "null is acceptable only for hold decisions."
        ),
    )
    take_profit_2: float | None = Field(
        default=None,
        description=(
            "Second (extended) take-profit price target.  Fully optional -- omit "
            "when a single-target trade is preferred."
        ),
    )
    risk_usd: float | None = Field(
        default=None,
        description=(
            "Dollar risk on the trade, computed as (entry - stop_loss) * position_size.  "
            "Should equal approximately 1% of account equity per risk-management rules."
        ),
    )
    r_multiple_target: float | None = Field(
        default=None,
        description=(
            "Reward-to-risk ratio target, e.g. 2.0 means TP1 is 2 R away from entry.  "
            "Used by downstream validators to sanity-check plan consistency."
        ),
    )


class StructuredReason(BaseModel):
    """Structured reasoning payload attached to every LLM tool call.

    Every field that carries ``Field(...)`` (no default) is **required** — the LLM
    must emit it; a missing field raises ``pydantic.ValidationError`` which the parser
    converts to ``StructuredOutputContractError`` (Step 4, PR-B2).

    **Content-quality floors** (asserted by ``scripts/probe_deepseek_structured.py``
    and by the unit tests in ``tests/agents/tools/test_structured_reason.py``):

      * ``len(market_context) >= 100`` chars — Step 0 observed mean ≈ 852 chars.
      * ``len(gates_passed) >= 1`` with at least one element of ``len >= 5`` chars.
      * ``len(invalidation_condition) >= 20`` chars.
      * If action is not hold: ``plan.entry != 0 and plan.stop_loss != 0 and
        plan.take_profit_1 != 0``.
      * ``len(justification) >= 200`` chars — Step 0 observed mean ≈ 1 385 chars.

    The ``Field(description=...)`` strings below are embedded verbatim into the
    tool JSON schema via ``model_json_schema()`` and are therefore read by the LLM
    at inference time — keep them concise but semantically precise.
    """

    market_context: str = Field(
        ...,
        min_length=1,
        description=(
            "YOUR synthesis of the current market regime and trading thesis in 2-4 "
            "sentences.  Do NOT restate the input numbers verbatim — interpret them.  "
            "Example: 'BTC is in a sustained uptrend with EMA20 > EMA50 > EMA200 and "
            "RSI holding above 55, suggesting continuation momentum.'"
        ),
    )
    gates_passed: list[str] = Field(
        default_factory=list,
        description=(
            "List of validation gates the trade setup has cleared, each as a "
            "human-readable sentence.  Follow the Alpha Arena convention: "
            "'<Gate name>: <evidence>'.  Example: "
            "'EMA alignment gate: EMA20 > EMA50 > EMA200 confirms primary uptrend'.  "
            "An empty list is valid only for hold decisions with no qualifying setup."
        ),
    )
    invalidation_condition: str = Field(
        ...,
        min_length=1,
        description=(
            "Specific price-action or indicator condition that would invalidate this "
            "decision.  Must be concrete and measurable, not vague.  "
            "Example: 'Daily close below 42 000 USDT would invalidate bullish bias.'"
        ),
    )
    plan: PlanBlock | None = Field(
        default=None,
        description=(
            "Numeric trade plan.  Required for open_position and partial_close calls "
            "with non-zero entry/SL/TP1.  MUST be null for hold_tool calls — hold "
            "decisions carry no entry, stop-loss, or take-profit."
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Probability estimate that this decision is correct, in [0.0, 1.0].  "
            "0.5 = coin-flip uncertainty; 0.8+ = high conviction.  "
            "Be calibrated: do not always output 0.8+."
        ),
    )
    justification: str = Field(
        ...,
        min_length=1,
        description=(
            "Full chain-of-thought justification for the decision.  Include: why this "
            "setup qualifies (or disqualifies), which indicators contributed, what "
            "risk-reward logic applies, and why alternatives were rejected.  "
            "Minimum 200 characters; Step 0 observed mean ≈ 1 385 chars — depth is "
            "valued here."
        ),
    )
    output_language: Literal["zh", "en"] = Field(
        default="zh",
        description=(
            "Language in which the human-readable fields (market_context, "
            "gates_passed, invalidation_condition, justification) are written.  "
            "Must match the OUTPUT_LANGUAGE environment variable (default 'zh').  "
            "Use 'zh' for Chinese output, 'en' for English output."
        ),
    )


# ---------------------------------------------------------------------------
# Module-level constant — pre-computed JSON schema for tool builders.
#
# Usage in tool factories (e.g. build_open_position_tool):
#
#   from omnitrade.agents.tools.structured_reason import STRUCTURED_REASON_JSON_SCHEMA
#
#   reason_param = {
#       "type": "object",
#       "description": "Structured reasoning for this decision",
#       **STRUCTURED_REASON_JSON_SCHEMA,
#   }
#
# The schema is computed once at import time so tool builders never call
# model_json_schema() repeatedly at request time.
# ---------------------------------------------------------------------------

STRUCTURED_REASON_JSON_SCHEMA: dict[str, object] = StructuredReason.model_json_schema()

__all__ = [
    "STRUCTURED_REASON_JSON_SCHEMA",
    "PlanBlock",
    "StructuredReason",
]

# ---------------------------------------------------------------------------
# DB column mapping (agent_decisions table extension, PR-B1 Step 2):
#   market_context         TEXT NULL  -- stores StructuredReason.market_context verbatim
#   gates_passed           TEXT NULL  -- stores json.dumps(StructuredReason.gates_passed)
#   invalidation_condition TEXT NULL  -- stores StructuredReason.invalidation_condition verbatim
#   plan                   TEXT NULL  -- stores json.dumps(PlanBlock.model_dump()) or None
#   confidence             REAL NULL  -- stores StructuredReason.confidence float
#   output_language        TEXT NULL  -- stores "zh" | "en" | NULL (legacy)
#
# JSON strategy: TEXT + json.dumps/loads (symmetric with existing actions_taken /
# market_analysis columns).  Do NOT use sa.JSON — SQLite dialect parity requires
# sa.Text() for all JSON columns (see alembic/env.py render_as_batch=True note).
# ---------------------------------------------------------------------------
