"""Unit tests for ToolQualityTracker — rolling window gating logic."""

from __future__ import annotations

import pytest

from omnitrade.infrastructure.mcp.quality_tracker import ToolQualityTracker


def test_unknown_tool_passes_gate() -> None:
    tracker = ToolQualityTracker()
    assert tracker.should_call("never_called") is True
    snap = tracker.snapshot("never_called")
    assert snap["samples"] == 0
    assert snap["success_rate"] == 1.0


def test_cold_start_below_min_samples_always_passes() -> None:
    tracker = ToolQualityTracker(min_samples_to_gate=3)
    tracker.record("x", success=False, latency_ms=120)
    tracker.record("x", success=False, latency_ms=110)
    # Still fewer than min_samples -> still allowed.
    assert tracker.should_call("x") is True


def test_gate_closes_when_success_rate_drops() -> None:
    tracker = ToolQualityTracker(min_samples_to_gate=3, min_success_rate=0.5)
    for _ in range(5):
        tracker.record("flaky", success=False, latency_ms=50)
    assert tracker.should_call("flaky") is False
    snap = tracker.snapshot("flaky")
    assert snap["samples"] == 5
    assert snap["success_rate"] == 0.0


def test_rolling_window_drops_old_samples() -> None:
    tracker = ToolQualityTracker(window=3, min_samples_to_gate=1, min_success_rate=0.5)
    # 3 successes fill the window
    for _ in range(3):
        tracker.record("t", success=True, latency_ms=10)
    assert tracker.should_call("t") is True
    # Now 4 failures — the oldest success gets evicted each step.
    for _ in range(4):
        tracker.record("t", success=False, latency_ms=10)
    snap = tracker.snapshot("t")
    assert snap["samples"] == 3  # window cap
    assert snap["success_rate"] == 0.0
    assert tracker.should_call("t") is False


def test_mixed_samples_use_success_rate_threshold() -> None:
    tracker = ToolQualityTracker(min_samples_to_gate=4, min_success_rate=0.6)
    # 3 OK + 2 fail = 60% -> passes.
    for _ in range(3):
        tracker.record("m", success=True, latency_ms=5)
    for _ in range(2):
        tracker.record("m", success=False, latency_ms=5)
    assert tracker.should_call("m") is True
    # One more failure drops to 50% -> fails gate.
    tracker.record("m", success=False, latency_ms=5)
    assert tracker.should_call("m") is False


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        ToolQualityTracker(window=0)
    with pytest.raises(ValueError):
        ToolQualityTracker(min_success_rate=1.5)
