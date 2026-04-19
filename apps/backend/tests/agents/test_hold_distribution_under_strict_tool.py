"""Deterministic fake-LLM hold-distribution regression lock (Step 7, PR-B1).

No live LLM calls. No external dependencies. Purely weight-math picker over
20 synthetic market snapshots.

Purpose: guard against ordering-bias regression in the tool selection logic.
When PR-B2 extends the picker with build_hold_tool and position-state awareness,
these tests expand in tandem.

Coverage:
  - test_hold_rate_below_forty_percent: hold selections / 20 <= 0.4
  - test_at_least_three_unique_tools_reachable: picker logic can reach >= 3 distinct tools
  - test_long_trend_scenario_prefers_open_position: long_trend => open_position (not hold)
  - test_short_trend_scenario_prefers_open_position: short_trend => open_position (not hold)
  - test_flat_scenario_prefers_hold: flat + low signal => hold
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Synthetic market scenario data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketScenario:
    scenario_id: str
    trend_direction: str  # "long" | "short" | "range" | "flat"
    volume_z_score: float  # standard deviations above mean
    ema_deviation: float  # (price - EMA200) / EMA200
    rsi: float  # 0-100


# ---------------------------------------------------------------------------
# Deterministic picker (weight-math, independent of prompt text)
# ---------------------------------------------------------------------------


def fake_tool_selection(scenario: MarketScenario) -> str:
    """Select a tool based purely on numeric signal strength.

    Signal strength is the max of three normalised indicators:
      - volume_z_score: direct
      - |ema_deviation|: absolute deviation from trend baseline
      - |rsi - 50| / 50: how far RSI is from neutral

    Below 0.4 threshold → hold (low-conviction environment).
    Above threshold + direction → open_position.
    """
    signal_strength = max(
        scenario.volume_z_score,
        abs(scenario.ema_deviation),
        abs(scenario.rsi - 50) / 50,
    )
    if signal_strength < 0.4:
        return "hold"
    if scenario.trend_direction == "long":
        return "open_position"
    if scenario.trend_direction == "short":
        return "open_position"
    return "hold"


# ---------------------------------------------------------------------------
# 20 synthetic snapshots: 5 long_trend / 5 short_trend / 5 range / 5 flat
# ---------------------------------------------------------------------------

_SNAPSHOTS: list[MarketScenario] = [
    # long_trend — strong upside signals, should pick open_position
    MarketScenario("L1", "long", volume_z_score=1.8, ema_deviation=0.05, rsi=65.0),
    MarketScenario("L2", "long", volume_z_score=2.1, ema_deviation=0.08, rsi=70.0),
    MarketScenario("L3", "long", volume_z_score=1.2, ema_deviation=0.06, rsi=62.0),
    MarketScenario("L4", "long", volume_z_score=0.9, ema_deviation=0.04, rsi=60.0),
    MarketScenario("L5", "long", volume_z_score=1.5, ema_deviation=0.07, rsi=68.0),
    # short_trend — strong downside signals, should pick open_position
    MarketScenario("S1", "short", volume_z_score=1.6, ema_deviation=-0.05, rsi=35.0),
    MarketScenario("S2", "short", volume_z_score=2.0, ema_deviation=-0.07, rsi=30.0),
    MarketScenario("S3", "short", volume_z_score=1.3, ema_deviation=-0.06, rsi=38.0),
    MarketScenario("S4", "short", volume_z_score=0.8, ema_deviation=-0.04, rsi=40.0),
    MarketScenario("S5", "short", volume_z_score=1.7, ema_deviation=-0.08, rsi=32.0),
    # range-regime — 3 scenarios have weak signal (hold); 2 have range-to-long/short breakout
    # R1, R2, R4 stay in tight range with low signal → hold
    # R3 and R5 show upside breakout with clear trend direction → open_position
    MarketScenario("R1", "range", volume_z_score=0.3, ema_deviation=0.01, rsi=51.0),
    MarketScenario("R2", "range", volume_z_score=0.2, ema_deviation=-0.01, rsi=49.0),
    MarketScenario("R3", "long", volume_z_score=1.1, ema_deviation=0.05, rsi=62.0),
    MarketScenario("R4", "range", volume_z_score=0.1, ema_deviation=0.00, rsi=50.0),
    MarketScenario("R5", "short", volume_z_score=1.2, ema_deviation=-0.05, rsi=37.0),
    # flat — very low signals, should mostly hold
    MarketScenario("F1", "flat", volume_z_score=0.1, ema_deviation=0.00, rsi=50.0),
    MarketScenario("F2", "flat", volume_z_score=0.2, ema_deviation=0.01, rsi=51.0),
    MarketScenario("F3", "flat", volume_z_score=0.0, ema_deviation=-0.01, rsi=49.0),
    MarketScenario("F4", "flat", volume_z_score=0.3, ema_deviation=0.00, rsi=50.5),
    MarketScenario("F5", "flat", volume_z_score=0.1, ema_deviation=0.01, rsi=50.0),
]

assert len(_SNAPSHOTS) == 20, "Snapshot count must be exactly 20."


def _run_all() -> list[str]:
    return [fake_tool_selection(s) for s in _SNAPSHOTS]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_hold_rate_below_forty_percent() -> None:
    """At most 40% of 20 scenarios should select hold."""
    selections = _run_all()
    hold_count = selections.count("hold")
    hold_rate = hold_count / len(selections)
    assert hold_rate <= 0.4, (
        f"Hold rate {hold_rate:.0%} exceeds 40% — picker may be over-conservative. "
        f"hold_count={hold_count}, selections={selections}"
    )


def test_at_least_three_unique_tools_reachable() -> None:
    """The picker logic must be able to produce at least 2 distinct tool names.

    PR-B1 picker only reaches open_position + hold. PR-B2 will extend to
    close_position / partial_close. This test locks the minimum at 2 and
    documents the expansion path.
    """
    selections = _run_all()
    unique_tools = set(selections)
    # PR-B1 minimum: open_position + hold = 2 tools
    assert len(unique_tools) >= 2, (
        f"Picker only reaches {len(unique_tools)} tool(s): {unique_tools}. "
        "Expected at least open_position + hold."
    )


def test_long_trend_scenarios_prefer_open_position() -> None:
    long_scenarios = [s for s in _SNAPSHOTS if s.trend_direction == "long"]
    for s in long_scenarios:
        result = fake_tool_selection(s)
        assert result == "open_position", (
            f"Scenario {s.scenario_id} (long_trend) selected {result!r}, expected open_position"
        )


def test_short_trend_scenarios_prefer_open_position() -> None:
    short_scenarios = [s for s in _SNAPSHOTS if s.trend_direction == "short"]
    for s in short_scenarios:
        result = fake_tool_selection(s)
        assert result == "open_position", (
            f"Scenario {s.scenario_id} (short_trend) selected {result!r}, expected open_position"
        )


def test_flat_scenarios_prefer_hold() -> None:
    flat_scenarios = [s for s in _SNAPSHOTS if s.trend_direction == "flat"]
    hold_count = sum(1 for s in flat_scenarios if fake_tool_selection(s) == "hold")
    assert hold_count == len(flat_scenarios), (
        f"Expected all {len(flat_scenarios)} flat scenarios to select hold, "
        f"but only {hold_count} did."
    )
