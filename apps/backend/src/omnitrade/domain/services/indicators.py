"""Pure technical-indicator primitives (EMA / MACD / RSI / ATR).

Hand-rolled on numpy — no ``pandas-ta``, no ``ta-lib`` (plan v3 MF-6).
All functions are total, pure, deterministic, and return standard
Python ``list[float]``. Input lists shorter than the required warm-up
length return an empty list rather than raising so callers can treat
"insufficient data" uniformly.

References:
    EMA  — Exponential moving average with SMA seed
            (Hunter, "Statistics 101"; upstream parity).
    MACD — Appel, "The Moving Average Convergence/Divergence
            Trading Method" (1979); default (12, 26, 9).
    RSI  — Wilder, *New Concepts in Technical Trading Systems*
            (1978), chapter 4; Wilder smoothing (RMA).
    ATR  — Wilder (1978), chapter 2; TR then Wilder smoothing.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _ema_array(values: NDArray[np.float64], period: int) -> NDArray[np.float64]:
    """EMA with SMA seed over the first ``period`` observations.

    Returns an array aligned to ``values`` whose first ``period - 1``
    entries are NaN and whose ``[period-1]`` entry equals the SMA of
    ``values[0:period]``; subsequent entries follow the standard
    recursion ``ema[i] = alpha * x[i] + (1 - alpha) * ema[i-1]``.
    """
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if period <= 0 or n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed = float(values[:period].mean())
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


def ema(prices: list[float], period: int) -> list[float]:
    """Exponential moving average with SMA seed (Wilder/Hunter convention).

    Returns ``len(prices) - period + 1`` values once the SMA seed is
    reached; returns an empty list when ``len(prices) < period``.
    """
    if period <= 0 or len(prices) < period:
        return []
    arr = np.asarray(prices, dtype=np.float64)
    full = _ema_array(arr, period)
    return [float(x) for x in full[period - 1 :]]


def macd(
    prices: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """MACD line / signal line / histogram (Appel 1979).

    line      = EMA(fast)  - EMA(slow)
    signal    = EMA(line, signal)  (seeded on first ``signal`` values)
    histogram = line - signal

    All three returned lists share the same length, starting once the
    ``slow + signal - 1`` warm-up has elapsed. Returns ``([], [], [])``
    when input is too short.
    """
    if fast <= 0 or slow <= 0 or signal <= 0 or fast >= slow:
        return [], [], []
    required = slow + signal - 1
    if len(prices) < required:
        return [], [], []
    arr = np.asarray(prices, dtype=np.float64)
    ema_fast = _ema_array(arr, fast)
    ema_slow = _ema_array(arr, slow)
    line_full = ema_fast - ema_slow
    # Start the signal EMA from the first valid slow-EMA index (slow - 1).
    line_valid = line_full[slow - 1 :]
    signal_valid = _ema_array(line_valid, signal)
    # Align line/signal/hist to the indices where signal is defined.
    start = slow - 1 + signal - 1
    line_out = line_full[start:]
    signal_out = signal_valid[signal - 1 :]
    hist_out = line_out - signal_out
    return (
        [float(x) for x in line_out],
        [float(x) for x in signal_out],
        [float(x) for x in hist_out],
    )


def rsi(prices: list[float], period: int = 14) -> list[float]:
    """Relative Strength Index with Wilder smoothing (Wilder 1978 ch. 4).

    Standard formulation: first avg_gain/avg_loss is the SMA of the
    initial ``period`` price changes; subsequent values use the Wilder
    recurrence ``avg = (prev_avg * (period - 1) + curr) / period``.
    Returns ``len(prices) - period`` values; empty when too short.
    """
    if period <= 0 or len(prices) <= period:
        return []
    arr = np.asarray(prices, dtype=np.float64)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    out: list[float] = []

    def _rsi_value(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0 if ag > 0.0 else 50.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out.append(_rsi_value(avg_gain, avg_loss))
    for i in range(period, deltas.shape[0]):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period
        out.append(_rsi_value(avg_gain, avg_loss))
    return out


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Average True Range with Wilder smoothing (Wilder 1978 ch. 2).

    ``TR_i = max(high_i - low_i, |high_i - prev_close|,
    |low_i - prev_close|)``; for ``i == 0`` the TR is just
    ``high_0 - low_0`` (no previous close). The ATR seed equals the SMA
    of the first ``period`` TR values; later values use the Wilder
    recurrence. Returns an empty list when inputs disagree in length or
    are shorter than ``period + 1``.
    """
    n = len(closes)
    if period <= 0 or n <= period or len(highs) != n or len(lows) != n:
        return []
    h = np.asarray(highs, dtype=np.float64)
    low = np.asarray(lows, dtype=np.float64)
    c = np.asarray(closes, dtype=np.float64)
    prev_close = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum.reduce(
        [h - low, np.abs(h - prev_close), np.abs(low - prev_close)]
    )
    # First-bar TR has no prior close; convention uses high-low only.
    tr[0] = h[0] - low[0]
    avg = float(tr[1 : period + 1].mean())
    out: list[float] = [avg]
    for i in range(period + 1, n):
        avg = (avg * (period - 1) + float(tr[i])) / period
        out.append(avg)
    return out


__all__ = ["atr", "ema", "macd", "rsi"]
