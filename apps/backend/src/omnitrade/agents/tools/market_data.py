"""Market-data tools — fetch ticker / OHLCV candles from the exchange.

These are read-only; no repository writes. They wrap
``ExchangeClient.fetch_ticker`` and ``ExchangeClient.fetch_ohlcv``.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Symbol
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class FetchTickerArgs(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")


class FetchOHLCVArgs(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")
    timeframe: str = Field(description="Candle size, e.g. '1m', '5m', '1h'.")
    limit: int = Field(ge=1, le=500, description="Number of candles (<=500).")


def build_fetch_ticker_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _fetch_ticker(symbol: str) -> dict[str, Any]:
        with_context(logger).debug("tool.fetch_ticker", symbol=symbol)
        ticker = await exchange.fetch_ticker(Symbol(value=symbol))
        return dict(ticker)

    return StructuredTool.from_function(
        coroutine=_fetch_ticker,
        name="fetch_ticker",
        description="Fetch the latest ticker (last/bid/ask/volume) for a symbol.",
        args_schema=FetchTickerArgs,
    )


def build_fetch_ohlcv_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> dict[str, Any]:
        with_context(logger).debug(
            "tool.fetch_ohlcv", symbol=symbol, timeframe=timeframe, limit=limit
        )
        candles = await exchange.fetch_ohlcv(Symbol(value=symbol), timeframe=timeframe, limit=limit)
        return {"symbol": symbol, "timeframe": timeframe, "candles": candles}

    return StructuredTool.from_function(
        coroutine=_fetch_ohlcv,
        name="fetch_ohlcv",
        description=(
            "Fetch OHLCV candles [timestamp, open, high, low, close, volume] "
            "for a symbol at a given timeframe."
        ),
        args_schema=FetchOHLCVArgs,
    )


# ---------------------------------------------------------------------------
# Phase 8.4 — funding rate / order book / open interest
# ---------------------------------------------------------------------------


class FundingRateArgs(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")


class OrderBookArgs(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")
    depth: int = Field(default=20, ge=1, le=50, description="Depth levels (<=50).")


class OpenInterestArgs(BaseModel):
    symbol: str = Field(description="Trading pair, e.g. 'BTC_USDT'.")


def build_funding_rate_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _funding_rate(symbol: str) -> dict[str, Any]:
        with_context(logger).debug("tool.funding_rate", symbol=symbol)
        rate = await exchange.fetch_funding_rate(Symbol(value=symbol))
        return {"symbol": symbol, "funding_rate": str(rate)}

    return StructuredTool.from_function(
        coroutine=_funding_rate,
        name="fundingRate",
        description=(
            "Fetch the latest perpetual-swap funding rate for a symbol. "
            "Returned as a string Decimal (e.g. '0.0001' = 0.01%)."
        ),
        args_schema=FundingRateArgs,
    )


def build_order_book_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _order_book(symbol: str, depth: int = 20) -> dict[str, Any]:
        with_context(logger).debug("tool.order_book", symbol=symbol, depth=depth)
        book = await exchange.fetch_order_book(Symbol(value=symbol), depth=depth)
        return dict(book)

    return StructuredTool.from_function(
        coroutine=_order_book,
        name="orderBook",
        description=(
            "Fetch an L2 order-book snapshot: bids / asks as [[price, amount], ...] "
            "lists (depth capped at 50). Use for microstructure / liquidity checks."
        ),
        args_schema=OrderBookArgs,
    )


def build_open_interest_tool(exchange: ExchangeClient) -> StructuredTool:
    async def _open_interest(symbol: str) -> dict[str, Any]:
        with_context(logger).debug("tool.open_interest", symbol=symbol)
        oi = await exchange.fetch_open_interest(Symbol(value=symbol))
        return {"symbol": symbol, "open_interest": str(oi)}

    return StructuredTool.from_function(
        coroutine=_open_interest,
        name="openInterest",
        description=(
            "Fetch the current open interest for a perpetual-swap contract. "
            "Returns Decimal-as-string in contract-amount units."
        ),
        args_schema=OpenInterestArgs,
    )


__all__ = [
    "FetchOHLCVArgs",
    "FetchTickerArgs",
    "FundingRateArgs",
    "OpenInterestArgs",
    "OrderBookArgs",
    "build_fetch_ohlcv_tool",
    "build_fetch_ticker_tool",
    "build_funding_rate_tool",
    "build_open_interest_tool",
    "build_order_book_tool",
]
