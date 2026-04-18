"""Smoke tests for the 6 Phase-8.4 ``ExchangeClient`` methods.

ccxt is mocked via ``unittest.mock.AsyncMock``; these tests verify
symbol translation + Decimal precision + Order shape, not live network.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from omnitrade.domain.entities import Order
from omnitrade.domain.value_objects import Symbol
from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange


def _make_exchange() -> CCXTExchange:
    ex = CCXTExchange(
        exchange_id="gate",
        api_key="dummy",
        api_secret="dummy",
        testnet=True,
    )
    return ex


@pytest.mark.asyncio
async def test_fetch_funding_rate_decimal() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_funding_rate = AsyncMock(return_value={"fundingRate": 0.0001})
    rate = await ex.fetch_funding_rate(Symbol(value="BTC_USDT"))
    assert rate == Decimal("0.0001")
    ex._exchange.fetch_funding_rate.assert_awaited_once()
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_funding_rate_missing_rate_raises() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_funding_rate = AsyncMock(return_value={})
    with pytest.raises(ValueError, match="no fundingRate"):
        await ex.fetch_funding_rate(Symbol(value="BTC_USDT"))
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_order_book_shape() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_order_book = AsyncMock(
        return_value={
            "bids": [[68000.0, 1.5], [67999.5, 2.0], [67999.0, 0.5]],
            "asks": [[68001.0, 1.0], [68001.5, 2.5]],
            "timestamp": 1700000000000,
        }
    )
    book = await ex.fetch_order_book(Symbol(value="BTC_USDT"), depth=2)
    assert book["symbol"] == "BTC_USDT"
    # Depth trims bid/ask lists.
    assert book["bids"] == [[68000.0, 1.5], [67999.5, 2.0]]
    assert book["asks"] == [[68001.0, 1.0], [68001.5, 2.5]]
    assert book["timestamp"] == 1700000000000
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_open_interest_prefers_amount() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_open_interest = AsyncMock(
        return_value={"openInterestAmount": 1234.5, "openInterestValue": 999999.0}
    )
    oi = await ex.fetch_open_interest(Symbol(value="BTC_USDT"))
    assert oi == Decimal("1234.5")
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_open_interest_falls_back_to_value() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_open_interest = AsyncMock(
        return_value={"openInterestValue": 999.0}
    )
    oi = await ex.fetch_open_interest(Symbol(value="BTC_USDT"))
    assert oi == Decimal("999.0")
    await ex.close()


def _ccxt_order(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "o-123",
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "status": "open",
        "price": 67000.0,
        "amount": 1.0,
        "remaining": 1.0,
        "timestamp": 1700000000000,
        **overrides,
    }


@pytest.mark.asyncio
async def test_fetch_open_orders_translates_to_domain() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_open_orders = AsyncMock(
        return_value=[
            _ccxt_order(id="o-1"),
            _ccxt_order(id="o-2", side="sell", status="partially_filled"),
        ]
    )
    orders = await ex.fetch_open_orders()
    assert len(orders) == 2
    assert isinstance(orders[0], Order)
    assert orders[0].id == "o-1"
    assert orders[0].side == "long"
    assert orders[0].status == "open"
    assert orders[1].side == "short"
    assert orders[1].status == "partially_filled"
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_order_returns_none_on_error() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_order = AsyncMock(side_effect=Exception("OrderNotFound"))
    result = await ex.fetch_order("o-missing", Symbol(value="BTC_USDT"))
    assert result is None
    await ex.close()


@pytest.mark.asyncio
async def test_fetch_order_maps_closed_to_filled() -> None:
    ex = _make_exchange()
    ex._exchange.fetch_order = AsyncMock(
        return_value=_ccxt_order(status="closed", remaining=0.0)
    )
    order = await ex.fetch_order("o-123", Symbol(value="BTC_USDT"))
    assert order is not None
    assert order.status == "filled"
    assert order.remaining == Decimal("0.0")
    await ex.close()


@pytest.mark.asyncio
async def test_cancel_order_returns_true() -> None:
    ex = _make_exchange()
    ex._exchange.cancel_order = AsyncMock(return_value={"id": "o-1", "status": "canceled"})
    ok = await ex.cancel_order("o-1", Symbol(value="BTC_USDT"))
    assert ok is True
    ex._exchange.cancel_order.assert_awaited_once()
    await ex.close()
