"""Backtest harness — Agno-driven historical replay of the trading loop.

Composes :class:`BacktestExchange` + :class:`HistoricalOHLCV` + an
Agno-backed ``ThinkFn`` (built by :func:`build_backtest_think_fn`) so the
same Decision schema the live cycle produces can be exercised against
historical candles without hitting the real exchange.

Imports nothing from ``api/`` or ``main.py`` — the backtest is a
standalone CLI (``python -m omnitrade.backtest``) and must not depend on
the FastAPI container.
"""

from __future__ import annotations

from omnitrade.backtest.agno_think import build_backtest_think_fn
from omnitrade.backtest.cassette import CassetteMode, cassette_context
from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.data_source import HistoricalOHLCV
from omnitrade.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    OHLCVDataSource,
    ThinkFn,
)
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.backtest.metrics import compute_metrics

__all__ = [
    "BacktestClock",
    "BacktestEngine",
    "BacktestExchange",
    "BacktestResult",
    "CassetteMode",
    "HistoricalOHLCV",
    "OHLCVDataSource",
    "ThinkFn",
    "build_backtest_think_fn",
    "cassette_context",
    "compute_metrics",
]
