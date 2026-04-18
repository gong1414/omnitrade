"""Pure ``compute_signals`` — OHLCV → ``TradingSignal``.

No I/O, no async. Given a deterministic OHLCV series this function is
100% reproducible (byte-exact between runs). Funding / open interest
are out of scope for Phase 8.2 (those live on ExchangeClient method
handlers landing in Phase 8.4); they are emitted as ``None``.

OHLCV row shape (ccxt unified): ``[timestamp_ms, open, high, low, close, volume]``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from omnitrade.domain.entities import TradingSignal
from omnitrade.domain.services.indicators import atr, ema, macd, rsi


def _last(values: list[float]) -> float | None:
    return values[-1] if values else None


def compute_signals(
    ohlcv: list[list[float]],
    symbol: str,
    timestamp: datetime,
) -> TradingSignal:
    """Derive a ``TradingSignal`` row from an OHLCV window.

    Args:
        ohlcv: Candle list in ccxt unified order
            ``[ts_ms, open, high, low, close, volume]``. Short windows
            simply yield ``None`` for the indicators whose warm-up has
            not elapsed; the ``price`` / ``volume`` fields always fall
            back to the last candle (or ``0`` for empty input).
        symbol: Contract symbol (e.g. ``"BTC_USDT"``).
        timestamp: Signal row timestamp (tz-aware).

    Returns:
        A frozen ``TradingSignal`` domain entity.
    """
    highs = [row[2] for row in ohlcv]
    lows = [row[3] for row in ohlcv]
    closes = [row[4] for row in ohlcv]
    volumes = [row[5] for row in ohlcv]

    last_close = closes[-1] if closes else 0.0
    last_volume = volumes[-1] if volumes else 0.0

    ema_20_series = ema(closes, 20)
    ema_50_series = ema(closes, 50)
    _macd_line, _macd_signal, macd_hist = macd(closes, 12, 26, 9)
    rsi_7_series = rsi(closes, 7)
    rsi_14_series = rsi(closes, 14)
    atr_3_series = atr(highs, lows, closes, 3)
    atr_14_series = atr(highs, lows, closes, 14)

    ema_20_last = _last(ema_20_series)
    ema_50_last = _last(ema_50_series)
    macd_last = _last(macd_hist)
    rsi_7_last = _last(rsi_7_series)
    rsi_14_last = _last(rsi_14_series)
    atr_3_last = _last(atr_3_series)
    atr_14_last = _last(atr_14_series)

    # TradingSignal requires non-null EMA-20 / MACD / RSI-7 / RSI-14; fall
    # back to ``last_close`` for EMA-20 and 0 for the others so short
    # warm-ups still produce a persistable row. EMA-50 / ATR-* are
    # genuinely optional on the schema and stay ``None`` when unavailable.
    return TradingSignal(
        symbol=symbol,
        timestamp=timestamp,
        price=Decimal(str(last_close)),
        ema_20=Decimal(str(ema_20_last if ema_20_last is not None else last_close)),
        ema_50=Decimal(str(ema_50_last)) if ema_50_last is not None else None,
        macd=Decimal(str(macd_last if macd_last is not None else 0.0)),
        rsi_7=Decimal(str(rsi_7_last if rsi_7_last is not None else 0.0)),
        rsi_14=Decimal(str(rsi_14_last if rsi_14_last is not None else 0.0)),
        volume=Decimal(str(last_volume)),
        open_interest=None,
        funding_rate=None,
        atr_3=Decimal(str(atr_3_last)) if atr_3_last is not None else None,
        atr_14=Decimal(str(atr_14_last)) if atr_14_last is not None else None,
    )


__all__ = ["compute_signals"]
