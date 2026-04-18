"""Close-path classifier — pure function, no I/O.

Classifies a Position into one of 5 ClosePath buckets based on current market
state and the strategy parameters. Buckets:
  - ``trailing_stop``  — trailing-stop ladder L3 → L2 → L1 resolution.
  - ``stop_loss``      — per-position override or strategy leverage-band threshold.
  - ``partial_profit`` — staged take-profit ladder with cumulative close %.
  - ``ai_decision``    — LLM-driven close via trade-execution tool.
  - ``none``           — no close this cycle.

The characterization gate validates this classifier against the frozen fixtures
in ``tests/fixtures/frozen/baseline_decisions/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from omnitrade.domain.entities import Position
from omnitrade.domain.enums import ClosePath


@dataclass(frozen=True)
class StopLossParams:
    """Per-leverage-band stop-loss thresholds (from strategy stopLoss config)."""

    low: Decimal  # threshold for low leverage (< mid_thresh)
    mid: Decimal  # threshold for mid leverage
    high: Decimal  # threshold for high leverage (>= high_thresh)
    mid_leverage_threshold: int = 10  # leverage < this → low band
    high_leverage_threshold: int = 20  # leverage >= this → high band


@dataclass(frozen=True)
class TrailingStopLevel:
    """One trailing-stop level from the strategy config."""

    trigger: Decimal  # trailing_peak_pnl_pct must reach this to arm
    stop_at: Decimal  # close when current_pnl_percent drops to this


@dataclass(frozen=True)
class PartialProfitStage:
    """One partial-profit stage from the strategy config."""

    trigger: Decimal  # pnl% threshold to trigger this stage
    close_percent: Decimal  # cumulative % to close at this stage


def get_stop_loss_threshold(
    position: Position,
    sl_params: StopLossParams,
) -> Decimal:
    """Select the effective stop-loss threshold for a position.

    Threshold resolution order:
    1. If position.stop_loss is set (override), use it directly.
    2. Otherwise pick from strategy band based on leverage.

    The override may be positive (profit-protection floor set after a partial-profit
    stage) or negative (hard stop-loss). Both are valid and returned as-is.
    """
    if position.stop_loss is not None:
        return position.stop_loss

    if position.leverage < sl_params.mid_leverage_threshold:
        return sl_params.low
    if position.leverage >= sl_params.high_leverage_threshold:
        return sl_params.high
    return sl_params.mid


def classify_close_path(
    position: Position,
    current_pnl_percent: Decimal,
    sl_params: StopLossParams,
    trailing_levels: list[TrailingStopLevel],
    partial_stages: list[PartialProfitStage],
    enable_code_level_protection: bool,
    ai_decision: dict[str, Any] | None,
) -> ClosePath:
    """Classify which close path applies to a position given current market state.

    Evaluation order (highest priority first):
    1. partial_profit — next un-hit partial stage triggered (10s loop)
    2. trailing_stop  — only when enable_code_level_protection=True (10s loop)
    3. stop_loss      — pnl <= effective threshold (10s loop)
    4. ai_decision    — AI explicitly requested close (trading loop)
    5. none           — no close signal

    Args:
        position: Current position snapshot.
        current_pnl_percent: Current levered PnL% (positive=profit, negative=loss).
        sl_params: Stop-loss band parameters from strategy config.
        trailing_levels: List of trailing-stop levels (L1→L3), highest first.
        partial_stages: List of partial take-profit stages (stage1→3).
        enable_code_level_protection: True when strategy uses code-level monitors.
        ai_decision: Optional AI decision dict; must have {"action": "close", ...}
                     to trigger ai_decision path.

    Returns:
        ClosePath enum member.
    """
    # ── 1. Partial profit (highest priority among monitor-triggered paths) ── #
    # Find the first un-hit stage whose trigger <= current_pnl_percent.
    for stage in partial_stages:
        if (
            current_pnl_percent >= stage.trigger
            and position.cumulative_close_pct < stage.close_percent
        ):
            return ClosePath.PARTIAL_PROFIT

    # ── 2. Trailing stop (only when enableCodeLevelProtection=true) ────────── #
    if enable_code_level_protection:
        peak = position.trailing_peak_pnl_pct
        # Check levels from highest trigger to lowest (L3→L2→L1)
        for level in sorted(trailing_levels, key=lambda lvl: lvl.trigger, reverse=True):
            if peak >= level.trigger and current_pnl_percent <= level.stop_at:
                return ClosePath.TRAILING_STOP

    # ── 3. Stop loss ─────────────────────────────────────────────────────────── #
    threshold = get_stop_loss_threshold(position, sl_params)
    if current_pnl_percent <= threshold:
        return ClosePath.STOP_LOSS

    # ── 4. AI decision ────────────────────────────────────────────────────────── #
    if ai_decision is not None and ai_decision.get("action") == "close":
        return ClosePath.AI_DECISION

    # ── 5. No close ──────────────────────────────────────────────────────────── #
    return ClosePath.NONE
