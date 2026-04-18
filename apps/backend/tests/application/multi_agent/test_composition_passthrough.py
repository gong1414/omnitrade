"""Unit tests for ``application.multi_agent.composition.build_think_fn`` (Phase 8.1).

The 8.1 composition is a passthrough enricher — the 8.5a expansion adds
multi-agent roster assembly. These tests pin the passthrough semantics
so cassette replay stays byte-exact when the kill-switch is off.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from omnitrade.application.multi_agent.composition import build_think_fn
from omnitrade.config import Settings
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache


class _StubExchange:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def fetch_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        limit: int = 100,
    ) -> list[list[float]]:
        self.calls.append((symbol.value, timeframe))
        return [[0.0, 1.0, 1.0, 1.0, 1.0, 10.0] for _ in range(3)]


def _make_fetcher() -> tuple[MultiTimeframeFetcher, _StubExchange]:
    exchange = _StubExchange()
    cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    fetcher = MultiTimeframeFetcher(
        exchange=exchange,  # type: ignore[arg-type]
        cache=cache,
    )
    return fetcher, exchange


def _make_market() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT", "ETH_USDT"],
        tickers={"BTC_USDT": Decimal("68000"), "ETH_USDT": Decimal("3500")},
    )


@pytest.mark.asyncio
async def test_kill_switch_off_returns_base_think_unchanged() -> None:
    fetcher, exchange = _make_fetcher()
    settings = Settings(multi_timeframe_enabled=False)

    async def base_think(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        return Decision(action="hold", reasoning="base")

    think_fn = build_think_fn(
        base_think,
        fetcher,
        settings,
        strategy_selector=lambda: StrategyName.SWING_TREND,
    )
    # With flag off, the wrapper short-circuits and returns the exact base fn.
    assert think_fn is base_think

    decision = await think_fn(_make_market(), [])
    assert decision.action == "hold"
    # Base think never touches the fetcher — exchange call count stays 0.
    assert exchange.calls == []


@pytest.mark.asyncio
async def test_kill_switch_on_enriches_market_snapshot() -> None:
    fetcher, exchange = _make_fetcher()
    settings = Settings(multi_timeframe_enabled=True)

    seen_markets: list[MarketSnapshot] = []

    async def base_think(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        seen_markets.append(market)
        return Decision(action="hold", reasoning="base")

    think_fn = build_think_fn(
        base_think,
        fetcher,
        settings,
        strategy_selector=lambda: StrategyName.SWING_TREND,
    )
    assert think_fn is not base_think

    await think_fn(_make_market(), [])

    assert len(seen_markets) == 1
    enriched = seen_markets[0]
    assert enriched.multi_tf_ohlcv is not None
    # arena-swingsmith → 4 TFs × 2 symbols = 8 exchange calls.
    assert set(enriched.multi_tf_ohlcv.keys()) == {"BTC_USDT", "ETH_USDT"}
    for per_symbol in enriched.multi_tf_ohlcv.values():
        assert list(per_symbol.keys()) == ["15m", "1h", "4h", "1d"]
    assert len(exchange.calls) == 8


@pytest.mark.asyncio
async def test_strategy_selector_drives_tf_set() -> None:
    fetcher, exchange = _make_fetcher()
    settings = Settings(multi_timeframe_enabled=True)

    async def base_think(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        return Decision(action="hold", reasoning="")

    think_fn = build_think_fn(
        base_think,
        fetcher,
        settings,
        strategy_selector=lambda: StrategyName.ULTRA_SHORT,
    )
    await think_fn(_make_market(), [])
    # arena-scalper → 4 TFs × 2 symbols = 8 calls, but TFs are 1m/3m/5m/15m.
    tfs_called = {tf for _, tf in exchange.calls}
    assert tfs_called == {"1m", "3m", "5m", "15m"}
