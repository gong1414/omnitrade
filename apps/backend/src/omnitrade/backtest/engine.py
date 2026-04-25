"""BacktestEngine — disabled stub during the Agno cutover.

The legacy engine drove ``run_cycle`` bar-by-bar via the LangGraph think
node + ``composition._build_tool_schemas`` + ``composition._tool_choice_for_strategy``.
All three of those collaborators were removed in Stage A of the Agno
hard-cutover (`/Users/daoyu/.claude/plans/mossy-frolicking-hickey.md`).

The full Agno port lives in Stage E. Until then any caller that imports
``BacktestEngine`` and tries to ``run()`` will get a clear NotImplementedError
that points at the plan file. The CLI binary at ``backtest/cli.py`` still
imports this module, so we keep the public symbols ``BacktestEngine`` and
``BacktestResult`` defined — they just refuse to execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class BacktestResult:
    """Placeholder so callers that destructure the result type still type-check."""

    strategy: str = ""
    symbols: list[str] = field(default_factory=list)
    timeframe: str = ""
    start: datetime | None = None
    end: datetime | None = None
    cycles_run: int = 0
    decisions: list[Any] = field(default_factory=list)
    trades: list[Any] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class BacktestEngine:
    """Stage A stub. The Agno port is tracked in Stage E of the cutover plan."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept the legacy constructor signature so import-time wiring in
        # ``backtest/cli.py`` does not crash. Execution still refuses.
        self._args = args
        self._kwargs = kwargs

    async def run(self) -> BacktestResult:
        raise NotImplementedError(
            "BacktestEngine is disabled while the Agno cutover lands. "
            "Tracked in Stage E of /Users/daoyu/.claude/plans/mossy-frolicking-hickey.md "
            "— port pending against Agno Agent + agno.models.deepseek.MockModel."
        )


__all__ = ["BacktestEngine", "BacktestResult"]
