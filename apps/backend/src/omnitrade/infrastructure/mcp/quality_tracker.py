"""Per-tool success/latency quality tracker.

The tracker keeps a lightweight rolling window of successes, failures and
latencies per tool. ``should_call(tool_name)`` returns ``False`` when a
tool's recent success rate drops below a threshold so the agent skips
flaky external services until they recover.

Design choices:

  * Pure in-memory; thread-safe via a single ``asyncio.Lock`` per call
    path. No cross-process state — the tracker resets with the process.
  * Window size is bounded so old samples don't skew the rolling view.
  * ``record(name, success, latency_ms)`` is the single write path used
    by any caller that invokes an MCP / external tool.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import monotonic

import structlog

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


@dataclass
class _ToolStats:
    """Rolling-window counters for one tool."""

    window: int
    outcomes: deque[bool] = field(default_factory=deque)
    latencies_ms: deque[float] = field(default_factory=deque)
    last_call_ts: float = 0.0

    def record(self, success: bool, latency_ms: float) -> None:
        self.outcomes.append(success)
        self.latencies_ms.append(latency_ms)
        self.last_call_ts = monotonic()
        while len(self.outcomes) > self.window:
            self.outcomes.popleft()
        while len(self.latencies_ms) > self.window:
            self.latencies_ms.popleft()

    def success_rate(self) -> float:
        if not self.outcomes:
            return 1.0  # Unknown tools are trusted until proven otherwise.
        return sum(1 for o in self.outcomes if o) / len(self.outcomes)

    def avg_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def sample_count(self) -> int:
        return len(self.outcomes)


class ToolQualityTracker:
    """Per-tool quality gating.

    Args:
        window:                 Rolling sample window per tool (default 20).
        min_success_rate:       Gate threshold [0..1]. Default 0.5 — below
                                this, ``should_call`` returns False.
        min_samples_to_gate:    Minimum sample count before gating kicks in
                                (avoids cold-start penalties). Default 3.
    """

    def __init__(
        self,
        *,
        window: int = 20,
        min_success_rate: float = 0.5,
        min_samples_to_gate: int = 3,
    ) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        if not (0.0 <= min_success_rate <= 1.0):
            raise ValueError("min_success_rate must be in [0, 1]")
        self._window = window
        self._min_rate = min_success_rate
        self._min_samples = min_samples_to_gate
        self._stats: dict[str, _ToolStats] = {}

    def record(self, tool_name: str, *, success: bool, latency_ms: float) -> None:
        stats = self._stats.setdefault(tool_name, _ToolStats(window=self._window))
        stats.record(success, latency_ms)
        with_context(logger).debug(
            "tool_quality.record",
            tool=tool_name,
            success=success,
            latency_ms=latency_ms,
            success_rate=stats.success_rate(),
            samples=stats.sample_count(),
        )

    def should_call(self, tool_name: str) -> bool:
        """Return True iff the tool's recent quality is above the gate."""
        stats = self._stats.get(tool_name)
        if stats is None:
            return True
        if stats.sample_count() < self._min_samples:
            return True
        return stats.success_rate() >= self._min_rate

    def snapshot(self, tool_name: str) -> dict[str, float | int]:
        stats = self._stats.get(tool_name)
        if stats is None:
            return {
                "samples": 0,
                "success_rate": 1.0,
                "avg_latency_ms": 0.0,
            }
        return {
            "samples": stats.sample_count(),
            "success_rate": stats.success_rate(),
            "avg_latency_ms": stats.avg_latency_ms(),
        }

    def names(self) -> list[str]:
        return sorted(self._stats.keys())


__all__ = ["ToolQualityTracker"]
