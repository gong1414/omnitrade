"""StructuredReason — minimal pre-merge preview schema (Step 0 of Phase 2 rewrite).

This is the draft schema exercised by ``scripts/probe_deepseek_structured.py``
against live DeepSeek V3.2 to prove the provider can reliably emit structured
reasoning under ``tool_choice="required"``. Step 1 of the consensus plan will
expand this (add ``output_language``, etc.); for Step 0 we only need the core
content fields the probe's triple-gate asserts against.

Do NOT import this module from production paths yet — Step 1 will replace it
with ``agents/tools/structured_output.py`` containing the full final schema.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PlanBlock(BaseModel):
    """Optional numeric trade plan. All fields optional because ``hold``
    decisions carry ``plan=None`` (no entry / SL / TP for a no-action cycle)."""

    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_usd: Optional[float] = None
    r_multiple_target: Optional[float] = None


class StructuredReason(BaseModel):
    """Structured reasoning payload attached to every tool call.

    Step 0 probes assert the following content-quality floor across 10 live
    DeepSeek probes (see ``scripts/probe_deepseek_structured.py``):

      * ``len(market_context) >= 100``
      * ``len(gates_passed) >= 1`` with at least one element of len >= 5
      * ``len(invalidation_condition) >= 20``
      * ``plan is not None`` when the tool is not hold (and its numeric
        fields non-zero)
      * ``len(justification) >= 200``
    """

    market_context: str = Field(..., min_length=1)
    gates_passed: list[str] = Field(default_factory=list)
    invalidation_condition: str = Field(..., min_length=1)
    plan: Optional[PlanBlock] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    justification: str = Field(..., min_length=1)


__all__ = ["PlanBlock", "StructuredReason"]
