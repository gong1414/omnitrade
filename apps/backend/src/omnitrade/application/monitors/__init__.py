"""5 scheduled monitors — unfolded per consensus plan §7 R1.

See ``application/monitors/README.md`` for the P1 waiver context: monitors
may compose domain + infrastructure because they sit at the boundary
between periodic scheduling and persistence. Domain purity (``domain/`` has
zero infra imports) is still enforced by the Phase-5 grep gates.

``register_monitors(scheduler, monitors)`` swaps every stub in
``infrastructure.scheduling.scheduler`` for the real Phase-5 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omnitrade.application.monitors.account_recorder_monitor import AccountRecorderMonitor
from omnitrade.application.monitors.clock import Clock, ClockProtocol, SystemClock
from omnitrade.application.monitors.partial_profit_monitor import PartialProfitMonitor
from omnitrade.application.monitors.stop_loss_monitor import StopLossMonitor
from omnitrade.application.monitors.trading_loop_monitor import TradingLoopMonitor
from omnitrade.application.monitors.trailing_stop_monitor import TrailingStopMonitor


@dataclass
class MonitorSet:
    """Holds the 5 Phase-5 monitors once constructed."""

    trading_loop: TradingLoopMonitor
    account_recorder: AccountRecorderMonitor
    trailing_stop: TrailingStopMonitor
    stop_loss: StopLossMonitor
    partial_profit: PartialProfitMonitor


def register_monitors(scheduler: Any, monitors: MonitorSet) -> None:
    """Replace each scheduler stub with the matching Phase-5 monitor tick.

    The monitor objects own their cadence; they receive the scheduler's
    ``replace_loop`` so each tick is a single ``await monitor.tick()`` call.
    Stop-loss shares the ``partial_profit_loop`` slot is wrong — instead the
    stop-loss monitor re-uses the 10-second ``partial_profit_loop`` cadence
    as a second call via ``add_job``. We keep the 5-loop file invariant by
    wrapping the stop-loss tick inside the partial-profit scheduler entry
    below… actually we register all 5 distinctly. The existing scheduler
    registers 5 loops; we register 5 monitors into the 5 slots:

      - trading_loop          → TradingLoopMonitor
      - trailing_stop_loop    → TrailingStopMonitor
      - partial_profit_loop   → PartialProfitMonitor
      - account_recorder_loop → AccountRecorderMonitor
      - news_fetch_loop       → StopLossMonitor  (repurposed 10s slot — the
        real TS bot runs a separate 10s setInterval for stop-loss, mirrored
        here onto the "news_fetch_loop" slot that was a Phase-3 stub.)
    """
    scheduler.replace_loop(
        "trading_loop",
        monitors.trading_loop.tick,
        monitors.trading_loop.interval_seconds,
    )
    scheduler.replace_loop(
        "account_recorder_loop",
        monitors.account_recorder.tick,
        monitors.account_recorder.interval_seconds,
    )
    scheduler.replace_loop(
        "trailing_stop_loop",
        monitors.trailing_stop.tick,
        monitors.trailing_stop.interval_seconds,
    )
    scheduler.replace_loop(
        "partial_profit_loop",
        monitors.partial_profit.tick,
        monitors.partial_profit.interval_seconds,
    )
    scheduler.replace_loop(
        "news_fetch_loop",
        monitors.stop_loss.tick,
        monitors.stop_loss.interval_seconds,
    )


__all__ = [
    "AccountRecorderMonitor",
    "Clock",
    "ClockProtocol",
    "MonitorSet",
    "PartialProfitMonitor",
    "StopLossMonitor",
    "SystemClock",
    "TradingLoopMonitor",
    "TrailingStopMonitor",
    "register_monitors",
]
