"""Backtest harness — standalone simulator for the trading loop.

Phase E1 (this package) wires the production ``trading_loop.run_cycle``
composition to an in-memory ``BacktestExchange`` + historical OHLCV
feed, so the same ``think_fn`` used in production can be evaluated on
historical candles without hitting the real exchange.

Imports nothing from ``api/`` / ``scheduler/`` / ``main.py`` — the
backtest is a standalone CLI (``python -m omnitrade.backtest``) and
must not depend on the FastAPI container.
"""

from __future__ import annotations

from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.data_source import HistoricalOHLCV
from omnitrade.backtest.engine import BacktestEngine, BacktestResult
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.backtest.llm_cache import CachedLLMClient
from omnitrade.backtest.metrics import compute_metrics

__all__ = [
    "BacktestClock",
    "BacktestEngine",
    "BacktestExchange",
    "BacktestResult",
    "CachedLLMClient",
    "HistoricalOHLCV",
    "compute_metrics",
]
