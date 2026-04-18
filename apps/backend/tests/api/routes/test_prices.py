"""GET /api/prices — batched tickers with 5s cache + bounds."""

from __future__ import annotations

from typing import Any

import pytest

from omnitrade.api.routes import prices as prices_route


class _SpyExchange:
    """Minimal exchange stub that counts fetch_ticker calls per symbol."""

    def __init__(self, payloads: dict[str, dict[str, Any]] | None = None) -> None:
        self.calls: list[str] = []
        self._payloads = payloads or {}

    async def fetch_ticker(self, symbol) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        s = str(symbol)
        self.calls.append(s)
        return self._payloads.get(
            s,
            {"symbol": s, "last": 100.0, "bid": 99.5, "ask": 100.5},
        )


@pytest.fixture(autouse=True)
def _clear_prices_cache() -> None:
    prices_route._clear_cache_for_tests()
    yield
    prices_route._clear_cache_for_tests()


@pytest.mark.asyncio
async def test_prices_single_symbol(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    spy = _SpyExchange({"BTC_USDT": {"last": 68000.0, "bid": 67995.0, "ask": 68005.0}})
    api_app.state.api_container.exchange = spy  # type: ignore[assignment]

    resp = await api_client.get("/api/prices?symbols=BTC_USDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["BTC_USDT"] == {"last": 68000.0, "bid": 67995.0, "ask": 68005.0}


@pytest.mark.asyncio
async def test_prices_batched_symbols(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    spy = _SpyExchange()
    api_app.state.api_container.exchange = spy  # type: ignore[assignment]

    resp = await api_client.get("/api/prices?symbols=BTC_USDT,ETH_USDT,SOL_USDT")
    body = resp.json()
    assert set(body.keys()) == {"BTC_USDT", "ETH_USDT", "SOL_USDT"}
    assert len(spy.calls) == 3


@pytest.mark.asyncio
async def test_prices_cache_suppresses_repeat_calls(api_app, api_client) -> None:  # type: ignore[no-untyped-def]
    spy = _SpyExchange()
    api_app.state.api_container.exchange = spy  # type: ignore[assignment]

    await api_client.get("/api/prices?symbols=BTC_USDT")
    await api_client.get("/api/prices?symbols=BTC_USDT")
    await api_client.get("/api/prices?symbols=BTC_USDT")
    # Only one actual exchange hit — the next two are cache-served.
    assert spy.calls.count("BTC_USDT") == 1


@pytest.mark.asyncio
async def test_prices_over_limit_rejected(api_client) -> None:  # type: ignore[no-untyped-def]
    symbols = ",".join(f"S{i}_USDT" for i in range(11))
    resp = await api_client.get(f"/api/prices?symbols={symbols}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_prices_empty_rejected(api_client) -> None:  # type: ignore[no-untyped-def]
    resp = await api_client.get("/api/prices?symbols=")
    # FastAPI Query with no default but with "" supplied — our handler 400s.
    assert resp.status_code == 400
