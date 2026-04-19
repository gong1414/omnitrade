"""Per-symbol indicator snapshot builder for LLM market context.

Wraps the pure-numpy primitives in
:mod:`omnitrade.domain.services.indicators` into a single
``Snapshot`` dict that describes the *current* indicator state of a
symbol. This is consumed by the PR-D Phase D1 ``_render_market_block``
rewrite so the LLM sees EMA / MACD / RSI / ATR values instead of just
tickers.

Design notes
------------
* **No pandas-ta / ta-lib dependency** — plan v3 MF-6 rule; the hand-rolled
  numpy primitives already live in ``domain.services.indicators``.
* **Snapshot = latest values only** — the LLM does not need full indicator
  series, just the current readings. We also keep the last 20 closes so
  the prompt can show a short trajectory.
* **Partial warm-up OK** — with < 200 candles ``ema200`` is ``None``
  (callers render as "—"). With < 50 candles the snapshot raises
  ``ValueError`` because EMA50 is the minimum useful warm-up.

OHLCV row shape is ccxt unified: ``[ts_ms, open, high, low, close, volume]``.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np

from omnitrade.domain.services.indicators import atr, ema, macd, rsi

_MIN_CANDLES_FOR_SNAPSHOT: int = 50
_EMA200_MIN_CANDLES: int = 200


class Snapshot(TypedDict, total=False):
    """Latest-value indicator snapshot for a single symbol on one TF.

    ``total=False`` because ``ema200`` may be absent when the OHLCV
    window is shorter than 200 candles. Required keys are always
    present; see ``snapshot_from_ohlcv`` for the invariants.
    """

    symbol: str
    price: float
    ema20: float
    ema50: float
    ema200: float | None
    rsi14: float
    macd: float
    atr14: float
    volume_ratio: float
    recent_closes: list[float]


def compute_ema(closes: list[float] | np.ndarray, period: int) -> float | None:
    """Return the latest EMA value or ``None`` if the warm-up isn't met."""
    series = ema(_to_list(closes), period)
    return series[-1] if series else None


def compute_rsi(closes: list[float] | np.ndarray, period: int = 14) -> float | None:
    """Return the latest RSI value or ``None`` if the warm-up isn't met."""
    series = rsi(_to_list(closes), period)
    return series[-1] if series else None


def compute_macd_hist(closes: list[float] | np.ndarray) -> float | None:
    """Return the latest MACD histogram (line - signal) or ``None``.

    Uses the standard Appel (12, 26, 9) configuration.
    """
    _line, _signal, hist = macd(_to_list(closes), 12, 26, 9)
    return hist[-1] if hist else None


def compute_atr(
    highs: list[float] | np.ndarray,
    lows: list[float] | np.ndarray,
    closes: list[float] | np.ndarray,
    period: int = 14,
) -> float | None:
    """Return the latest ATR value or ``None`` if the warm-up isn't met."""
    series = atr(_to_list(highs), _to_list(lows), _to_list(closes), period)
    return series[-1] if series else None


def compute_volume_ratio(
    volumes: list[float] | np.ndarray,
    lookback: int = 20,
) -> float:
    """Return ``current_volume / average(last N volumes)``.

    Falls back to ``1.0`` when there are fewer than ``lookback + 1``
    candles or when the average volume is zero — this keeps the
    prompt numerically stable without leaking ``NaN`` through to the
    rendered table.
    """
    vols = _to_list(volumes)
    if len(vols) < lookback + 1:
        return 1.0
    current = float(vols[-1])
    window = vols[-(lookback + 1) : -1]
    if not window:
        return 1.0
    avg = float(np.mean(window))
    if avg == 0.0:
        return 1.0
    return current / avg


def snapshot_from_ohlcv(
    symbol: str,
    ohlcv: list[list[float]],
    *,
    recent_closes_window: int = 20,
) -> Snapshot:
    """Build a single-TF ``Snapshot`` from a ccxt OHLCV window.

    Args:
        symbol: Contract symbol (e.g. ``"BTC_USDT"``).
        ohlcv: Candle list in ccxt unified order
            ``[ts_ms, open, high, low, close, volume]``. Must contain
            at least ``_MIN_CANDLES_FOR_SNAPSHOT`` (50) candles.
        recent_closes_window: Size of the trailing-close list appended
            to the snapshot (default 20, matching the LLM prompt).

    Returns:
        A :class:`Snapshot` dict with all indicator warm-ups that fit
        in the provided window. ``ema200`` is ``None`` when the window
        is shorter than 200 candles.

    Raises:
        ValueError: when ``ohlcv`` is empty or shorter than 50 candles,
            or when any indicator primitive cannot produce a value at
            the 50-candle minimum (defensive — mathematically EMA50 and
            RSI14 / ATR14 are all defined at 50 candles).
    """
    if not ohlcv:
        raise ValueError(f"snapshot_from_ohlcv: empty OHLCV for {symbol}")
    if len(ohlcv) < _MIN_CANDLES_FOR_SNAPSHOT:
        raise ValueError(
            f"snapshot_from_ohlcv: {symbol} has {len(ohlcv)} candles, "
            f"need >= {_MIN_CANDLES_FOR_SNAPSHOT}"
        )

    highs = [row[2] for row in ohlcv]
    lows = [row[3] for row in ohlcv]
    closes = [row[4] for row in ohlcv]
    volumes = [row[5] for row in ohlcv]

    ema20_last = compute_ema(closes, 20)
    ema50_last = compute_ema(closes, 50)
    ema200_last = compute_ema(closes, 200) if len(closes) >= _EMA200_MIN_CANDLES else None
    rsi14_last = compute_rsi(closes, 14)
    macd_last = compute_macd_hist(closes)
    atr14_last = compute_atr(highs, lows, closes, 14)
    vol_ratio = compute_volume_ratio(volumes, 20)

    # With >= 50 candles, EMA20 / EMA50 / RSI14 / ATR14 are all defined.
    # MACD requires 26 + 9 - 1 = 34, also defined. Guard defensively in case
    # upstream feeds shorter-but-nonempty arrays past the gate.
    if ema20_last is None or ema50_last is None:
        raise ValueError(f"snapshot_from_ohlcv: {symbol} EMA warm-up incomplete")
    if rsi14_last is None or atr14_last is None or macd_last is None:
        raise ValueError(f"snapshot_from_ohlcv: {symbol} indicator warm-up incomplete")

    price = float(closes[-1])
    recent = [float(c) for c in closes[-recent_closes_window:]]

    snap: Snapshot = {
        "symbol": symbol,
        "price": price,
        "ema20": float(ema20_last),
        "ema50": float(ema50_last),
        "ema200": float(ema200_last) if ema200_last is not None else None,
        "rsi14": float(rsi14_last),
        "macd": float(macd_last),
        "atr14": float(atr14_last),
        "volume_ratio": float(vol_ratio),
        "recent_closes": recent,
    }
    return snap


def _to_list(values: list[float] | np.ndarray) -> list[float]:
    """Normalise input to ``list[float]`` — the primitives expect lists."""
    if isinstance(values, np.ndarray):
        return [float(x) for x in values.tolist()]
    return [float(x) for x in values]


__all__ = [
    "Snapshot",
    "compute_atr",
    "compute_ema",
    "compute_macd_hist",
    "compute_rsi",
    "compute_volume_ratio",
    "snapshot_from_ohlcv",
]
