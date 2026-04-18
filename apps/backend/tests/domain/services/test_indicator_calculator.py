"""Unit tests for ``domain.services.indicator_calculator.compute_signals``."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from omnitrade.domain.entities import TradingSignal
from omnitrade.domain.services.indicator_calculator import compute_signals


def _build_ramp_ohlcv(n: int) -> list[list[float]]:
    """``[[ts_ms, open, high, low, close, volume], ...]`` with a strict ramp.

    Strict ramp → RSI saturates to 100, gives deterministic values for
    long-warm-up indicators.
    """
    out: list[list[float]] = []
    for i in range(n):
        close = float(i + 1)
        row = [
            i * 60_000,  # ts_ms
            close - 0.1,  # open
            close + 0.2,  # high
            close - 0.2,  # low
            close,  # close
            100.0 + float(i),  # volume
        ]
        out.append(row)
    return out


def test_returns_trading_signal_with_expected_scalar_shape() -> None:
    ts = datetime.now(tz=UTC)
    ohlcv = _build_ramp_ohlcv(60)
    sig = compute_signals(ohlcv, "BTC_USDT", ts)
    assert isinstance(sig, TradingSignal)
    assert sig.symbol == "BTC_USDT"
    assert sig.timestamp == ts
    # Last close = 60.0, last volume = 159.0
    assert sig.price == Decimal("60.0")
    assert sig.volume == Decimal("159.0")
    # Strictly increasing → RSI saturates at 100 for both periods.
    assert sig.rsi_7 == Decimal("100.0")
    assert sig.rsi_14 == Decimal("100.0")
    # EMA-20 / EMA-50 populated.
    assert sig.ema_20 is not None
    assert sig.ema_50 is not None


def test_short_input_falls_back_safely() -> None:
    ts = datetime.now(tz=UTC)
    ohlcv = _build_ramp_ohlcv(5)  # too short for EMA-50, MACD, RSI-14
    sig = compute_signals(ohlcv, "ETH_USDT", ts)
    # last close from the 5-bar ramp = 5.0
    assert sig.price == Decimal("5.0")
    # EMA-50 is genuinely optional → None
    assert sig.ema_50 is None
    # ATR-14 also unreachable → None
    assert sig.atr_14 is None
    # MACD / RSI fall back to 0 so the row is still persistable.
    assert sig.macd == Decimal("0.0")
    assert sig.rsi_7 == Decimal("0.0")
    assert sig.rsi_14 == Decimal("0.0")
    # EMA-20 degrades to last close when warm-up incomplete.
    assert sig.ema_20 == Decimal("5.0")


def test_empty_input_defaults_to_zero() -> None:
    ts = datetime.now(tz=UTC)
    sig = compute_signals([], "SOL_USDT", ts)
    assert sig.price == Decimal("0.0")
    assert sig.volume == Decimal("0.0")
    assert sig.ema_20 == Decimal("0.0")


def test_compute_is_reproducible() -> None:
    """Running compute_signals twice on the same input returns identical values."""
    ts = datetime.now(tz=UTC)
    ohlcv = _build_ramp_ohlcv(80)
    a = compute_signals(ohlcv, "BTC_USDT", ts)
    b = compute_signals(ohlcv, "BTC_USDT", ts)
    assert a == b
