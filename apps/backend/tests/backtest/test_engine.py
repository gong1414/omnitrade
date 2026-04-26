"""End-to-end smoke test for :class:`BacktestEngine` (post-Agno cutover).

Uses a stub data source + stub think_fn so the harness exercises every
pipe — pre-fetch → bar loop → think → execute → metrics — without
hitting Binance or DeepSeek. Designed to fail loudly if the engine's
dispatch contract drifts from production composition.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.engine import BacktestEngine
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.config import Settings
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem


class _StubData:
    """In-memory ``HistoricalOHLCV`` clone — returns a deterministic ramp."""

    def __init__(self, bars_per_window: int = 10) -> None:
        self._bars = bars_per_window

    async def load(
        self, symbol: str, timeframe: str, start_ms: int, end_ms: int
    ) -> list[list[float]]:
        step_ms = 4 * 60 * 60_000  # 4h
        return [
            [
                float(start_ms + i * step_ms),
                100.0 + i,
                101.0 + i,
                99.0 + i,
                100.0 + i,
                1000.0,
            ]
            for i in range(self._bars)
        ]

    async def close(self) -> None:
        return None


class _StubThink:
    """Open long at cycle 0, close at cycle 4, hold otherwise."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(
        self, market: MarketSnapshot, news: list[NewsItem]
    ) -> Decision:
        self.calls += 1
        if self.calls == 1:
            return Decision(
                action="open",
                symbol="BTC_USDT",
                side="long",
                size=Decimal("0.01"),
                leverage=2,
                reasoning="stub-open",
                confidence=Decimal("0.8"),
            )
        if self.calls == 5:
            return Decision(
                action="close", symbol="BTC_USDT", reasoning="stub-close"
            )
        return Decision(action="hold", reasoning="stub-hold")


@pytest.mark.asyncio
async def test_backtest_engine_smoke_open_close() -> None:
    settings = Settings()
    data = _StubData(bars_per_window=10)
    exchange = BacktestExchange(
        initial_balance_usdt=Decimal("10000"),
        data_source=data,
    )
    clock = BacktestClock(start=datetime(2026, 1, 1, tzinfo=UTC))
    think = _StubThink()

    engine = BacktestEngine(
        exchange=exchange,
        clock=clock,
        data_source=data,
        think_fn=think,
        settings=settings,
        symbols=["BTC_USDT"],
        timeframe="4h",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, 16, tzinfo=UTC),
    )
    result = await engine.run()

    assert result.cycles_run == 10
    assert len(result.decisions) == 10
    assert result.decisions[0].action == "open"
    assert result.decisions[4].action == "close"
    # First trade must be an open, second a close — nothing in between.
    trade_types = [t.type for t in result.trades]
    assert trade_types == ["open", "close"]
    assert "Backtest report" in result.to_markdown()
    # Metrics dictionary is well-shaped even on a tiny window.
    assert "total_return_pct" in result.metrics
    assert "trade_count" in result.metrics


@pytest.mark.asyncio
async def test_backtest_engine_rejects_zero_window() -> None:
    settings = Settings()
    data = _StubData()
    exchange = BacktestExchange(
        initial_balance_usdt=Decimal("10000"),
        data_source=data,
    )
    clock = BacktestClock(start=datetime(2026, 1, 1, tzinfo=UTC))

    async def _hold(_m: Any, _n: Any) -> Decision:
        return Decision(action="hold")

    with pytest.raises(ValueError, match="end .* must be after start"):
        BacktestEngine(
            exchange=exchange,
            clock=clock,
            data_source=data,
            think_fn=_hold,
            settings=settings,
            symbols=["BTC_USDT"],
            start=datetime(2026, 1, 2, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        )
