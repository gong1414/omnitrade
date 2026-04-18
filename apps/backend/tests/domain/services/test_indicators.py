"""Unit tests for Phase 8.2 indicator primitives (EMA / MACD / RSI / ATR)."""

from __future__ import annotations

import math

from omnitrade.domain.services.indicators import atr, ema, macd, rsi


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=0, abs_tol=tol)


# ── EMA ────────────────────────────────────────────────────────────────


def test_ema_short_input_returns_empty() -> None:
    assert ema([1.0, 2.0, 3.0], period=5) == []


def test_ema_constant_input_equals_constant() -> None:
    out = ema([10.0] * 10, period=4)
    assert all(_approx(x, 10.0) for x in out)
    # Starts once SMA seed is reached: len = n - period + 1
    assert len(out) == 7


def test_ema_known_sequence() -> None:
    # alpha = 2 / (3+1) = 0.5
    prices = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ema(prices, period=3)
    # Seed SMA of first 3 = 2.0; then 0.5 * 4 + 0.5 * 2 = 3.0; 0.5 * 5 + 0.5 * 3 = 4.0
    assert len(out) == 3
    assert _approx(out[0], 2.0)
    assert _approx(out[1], 3.0)
    assert _approx(out[2], 4.0)


def test_ema_invalid_period_returns_empty() -> None:
    assert ema([1.0, 2.0, 3.0], period=0) == []
    assert ema([1.0, 2.0, 3.0], period=-5) == []


# ── MACD ───────────────────────────────────────────────────────────────


def test_macd_too_short_returns_empty_triple() -> None:
    line, sig, hist = macd([1.0, 2.0, 3.0])
    assert line == [] and sig == [] and hist == []


def test_macd_line_equals_hist_plus_signal() -> None:
    # Use a deterministic ramp long enough for 26+9-1 warm-up.
    prices = [float(i) for i in range(1, 101)]
    line, signal_line, hist = macd(prices, fast=12, slow=26, signal=9)
    assert len(line) == len(signal_line) == len(hist) > 0
    for line_value, sig_v, h in zip(line, signal_line, hist, strict=True):
        assert _approx(h, line_value - sig_v, tol=1e-10)


def test_macd_invalid_args_returns_empty() -> None:
    assert macd([1.0] * 100, fast=30, slow=12) == ([], [], [])
    assert macd([1.0] * 100, fast=0) == ([], [], [])


# ── RSI ────────────────────────────────────────────────────────────────


def test_rsi_all_gains_saturates_to_100() -> None:
    out = rsi([float(i) for i in range(1, 30)], period=14)
    assert len(out) == 29 - 14
    for v in out:
        assert _approx(v, 100.0)


def test_rsi_all_losses_saturates_to_zero() -> None:
    out = rsi([float(30 - i) for i in range(29)], period=14)
    assert len(out) == 29 - 14
    for v in out:
        assert _approx(v, 0.0)


def test_rsi_length_is_n_minus_period() -> None:
    out = rsi([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0], period=3)
    assert len(out) == 8 - 3


def test_rsi_short_input_returns_empty() -> None:
    assert rsi([1.0, 2.0, 3.0], period=14) == []
    assert rsi([], period=14) == []


# ── ATR ────────────────────────────────────────────────────────────────


def test_atr_constant_candles_yields_zero() -> None:
    highs = [10.0] * 20
    lows = [10.0] * 20
    closes = [10.0] * 20
    out = atr(highs, lows, closes, period=14)
    for v in out:
        assert _approx(v, 0.0)


def test_atr_mismatched_lengths_returns_empty() -> None:
    assert atr([1.0, 2.0], [1.0], [1.0, 2.0], period=1) == []


def test_atr_short_input_returns_empty() -> None:
    assert atr([1.0, 2.0], [0.5, 1.0], [0.8, 1.5], period=14) == []


def test_atr_length_matches_formula() -> None:
    # period=3 with 10 candles → len = 10 - period = 7 (seed at index `period`
    # then n - period - 1 recurrence steps → +1 for seed = n - period).
    highs = [float(i) + 1 for i in range(10)]
    lows = [float(i) for i in range(10)]
    closes = [float(i) + 0.5 for i in range(10)]
    out = atr(highs, lows, closes, period=3)
    assert len(out) == 10 - 3
