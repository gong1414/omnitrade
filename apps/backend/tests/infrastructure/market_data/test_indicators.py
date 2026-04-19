"""Unit tests for ``infrastructure.market_data.indicators``.

Covers:
  * ``snapshot_from_ohlcv`` happy-path invariants (all fields populated,
    price = latest close, recent_closes trimmed to last 20).
  * EMA200 degrades to ``None`` below the 200-candle warm-up.
  * Empty / too-short input raises ``ValueError``.
  * ``compute_volume_ratio`` edge cases (short input, zero average).
"""

from __future__ import annotations

import math

import pytest

from omnitrade.infrastructure.market_data.indicators import (
    compute_ema,
    compute_macd_hist,
    compute_rsi,
    compute_volume_ratio,
    snapshot_from_ohlcv,
)


def _ohlcv_ramp(n: int, *, start: float = 100.0, step: float = 1.0) -> list[list[float]]:
    """Build a deterministic monotonically-rising OHLCV window.

    Each candle has ``open = close - step/2``, ``high = close + 1``,
    ``low = close - 1``, ``volume = 10`` (constant so volume_ratio = 1).
    """
    out: list[list[float]] = []
    for i in range(n):
        close = start + i * step
        open_ = close - step / 2.0
        high = close + 1.0
        low = close - 1.0
        out.append([i * 60_000.0, open_, high, low, close, 10.0])
    return out


# ── snapshot_from_ohlcv ────────────────────────────────────────────────


def test_snapshot_happy_path_all_fields_populated() -> None:
    ohlcv = _ohlcv_ramp(250)
    snap = snapshot_from_ohlcv("BTC_USDT", ohlcv)

    assert snap["symbol"] == "BTC_USDT"
    # Last close = 100 + 249 = 349.0
    assert snap["price"] == pytest.approx(349.0)
    # Monotonically rising → EMAs trail the price but are positive.
    assert snap["ema20"] > 0.0
    assert snap["ema50"] > 0.0
    assert snap["ema200"] is not None and snap["ema200"] > 0.0
    # Strictly-rising window → RSI saturates near 100.
    assert snap["rsi14"] == pytest.approx(100.0)
    # Monotonic uptrend → MACD histogram is finite (sign depends on
    # fast/slow spacing but at 250 candles it's settled close to 0).
    assert math.isfinite(snap["macd"])
    # ATR14 is the true range average; for step=1 ramp with h-l=2 it's
    # bounded by the TR max of ~3.
    assert 0.0 < snap["atr14"] < 5.0
    # Constant volume → ratio ≈ 1.0.
    assert snap["volume_ratio"] == pytest.approx(1.0)
    # recent_closes: last 20 closes, ascending.
    closes = snap["recent_closes"]
    assert len(closes) == 20
    assert closes == sorted(closes)


def test_snapshot_under_200_candles_sets_ema200_none() -> None:
    ohlcv = _ohlcv_ramp(100)
    snap = snapshot_from_ohlcv("ETH_USDT", ohlcv)

    assert snap["ema200"] is None
    # EMA20 / EMA50 still populated at 100 candles.
    assert snap["ema20"] > 0.0
    assert snap["ema50"] > 0.0


def test_snapshot_exactly_50_candles_populates_ema50_but_not_ema200() -> None:
    ohlcv = _ohlcv_ramp(50)
    snap = snapshot_from_ohlcv("SOL_USDT", ohlcv)

    assert snap["ema50"] > 0.0
    assert snap["ema200"] is None


def test_snapshot_empty_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="empty OHLCV"):
        snapshot_from_ohlcv("BTC_USDT", [])


def test_snapshot_too_short_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="need >= 50"):
        snapshot_from_ohlcv("BTC_USDT", _ohlcv_ramp(20))


def test_snapshot_recent_closes_trims_to_window() -> None:
    ohlcv = _ohlcv_ramp(60)
    snap = snapshot_from_ohlcv("BTC_USDT", ohlcv, recent_closes_window=5)
    assert len(snap["recent_closes"]) == 5
    # Trimmed window is strictly the last 5 closes.
    expected = [100.0 + i for i in range(55, 60)]
    for actual, want in zip(snap["recent_closes"], expected, strict=True):
        assert actual == pytest.approx(want)


# ── primitive wrappers ─────────────────────────────────────────────────


def test_compute_ema_too_short_returns_none() -> None:
    assert compute_ema([1.0, 2.0], period=5) is None


def test_compute_ema_known_sequence() -> None:
    # Matches the primitive-level known sequence test in test_indicators.
    out = compute_ema([1.0, 2.0, 3.0, 4.0, 5.0], period=3)
    assert out == pytest.approx(4.0)


def test_compute_rsi_too_short_returns_none() -> None:
    assert compute_rsi([1.0, 2.0, 3.0], period=14) is None


def test_compute_macd_hist_too_short_returns_none() -> None:
    assert compute_macd_hist([1.0] * 10) is None


# ── compute_volume_ratio ───────────────────────────────────────────────


def test_volume_ratio_short_input_returns_one() -> None:
    # < lookback + 1 → default 1.0 (no NaN leakage).
    assert compute_volume_ratio([1.0, 2.0, 3.0], lookback=20) == 1.0


def test_volume_ratio_zero_average_returns_one() -> None:
    # 21 zeros → average is zero → guarded to 1.0.
    assert compute_volume_ratio([0.0] * 21, lookback=20) == 1.0


def test_volume_ratio_double_the_average() -> None:
    # 20 volumes of 10, then one candle at 20 → ratio = 2.0.
    vols = [10.0] * 20 + [20.0]
    assert compute_volume_ratio(vols, lookback=20) == pytest.approx(2.0)
