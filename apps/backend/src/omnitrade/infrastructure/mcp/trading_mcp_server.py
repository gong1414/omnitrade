"""OmniTrade Trading MCP Server — exposes exchange/market tools as MCP tools.

Run as stdio MCP server:
    python -m omnitrade.infrastructure.mcp.trading_mcp_server

AnyTool discovers these tools via config_mcp.json and routes trading-related
queries to them. Adding a new exchange (e.g. OKX) or asset class (e.g. stocks)
only requires adding new MCP tools here — no changes to the think loop.
"""

from __future__ import annotations

import json
import math
import os
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omnitrade-trading")


def _get_exchange() -> Any:
    """Construct an ExchangeClient from environment variables."""
    from omnitrade.config import Settings
    from omnitrade.domain.value_objects import Symbol
    from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange

    settings = Settings()
    if settings.exchange == "okx":
        api_key = settings.okx_api_key.get_secret_value() if settings.okx_api_key else ""
        api_secret = settings.okx_api_secret.get_secret_value() if settings.okx_api_secret else ""
        passphrase = (
            settings.okx_api_passphrase.get_secret_value() if settings.okx_api_passphrase else None
        )
        return CCXTExchange(
            exchange_id="okx",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.okx_use_testnet,
            passphrase=passphrase,
        )
    api_key = settings.gate_api_key.get_secret_value() if settings.gate_api_key else ""
    api_secret = settings.gate_api_secret.get_secret_value() if settings.gate_api_secret else ""
    return CCXTExchange(
        exchange_id="gate",
        api_key=api_key,
        api_secret=api_secret,
        testnet=settings.gate_use_testnet,
    )


def _get_symbol_module() -> Any:
    from omnitrade.domain.value_objects import Symbol
    return Symbol


# ---------------------------------------------------------------------------
# Market data tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def fetch_ticker(symbol: str) -> str:
    """Fetch the latest ticker (last/bid/ask/volume) for a symbol.

    Args:
        symbol: Trading pair, e.g. 'BTC_USDT'.
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        ticker = await exchange.fetch_ticker(Symbol(value=symbol))
        return json.dumps(dict(ticker), default=str)
    finally:
        await exchange.close()


@mcp.tool()
async def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> str:
    """Fetch OHLCV candles [timestamp, open, high, low, close, volume].

    Args:
        symbol: Trading pair, e.g. 'BTC_USDT'.
        timeframe: Candle size, e.g. '1m', '5m', '15m', '1h', '4h'.
        limit: Number of candles to return (max 500).
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        candles = await exchange.fetch_ohlcv(
            Symbol(value=symbol), timeframe=timeframe, limit=min(limit, 500)
        )
        return json.dumps({"symbol": symbol, "timeframe": timeframe, "candles": candles}, default=str)
    finally:
        await exchange.close()


@mcp.tool()
async def funding_rate(symbol: str) -> str:
    """Fetch the latest perpetual-swap funding rate for a symbol.

    Args:
        symbol: Trading pair, e.g. 'BTC_USDT'.
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        rate = await exchange.fetch_funding_rate(Symbol(value=symbol))
        return json.dumps({"symbol": symbol, "funding_rate": str(rate)})
    finally:
        await exchange.close()


@mcp.tool()
async def order_book(symbol: str, depth: int = 20) -> str:
    """Fetch an L2 order-book snapshot: bids / asks as [[price, amount], ...].

    Args:
        symbol: Trading pair, e.g. 'BTC_USDT'.
        depth: Depth levels (1-50).
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        book = await exchange.fetch_order_book(Symbol(value=symbol), depth=min(depth, 50))
        return json.dumps(dict(book), default=str)
    finally:
        await exchange.close()


@mcp.tool()
async def open_interest(symbol: str) -> str:
    """Fetch the current open interest for a perpetual-swap contract.

    Args:
        symbol: Trading pair, e.g. 'BTC_USDT'.
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        oi = await exchange.fetch_open_interest(Symbol(value=symbol))
        return json.dumps({"symbol": symbol, "open_interest": str(oi)})
    finally:
        await exchange.close()


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def account_snapshot() -> str:
    """Fetch the current account balance snapshot (total / free / uPnL)."""
    exchange = _get_exchange()
    try:
        snap = await exchange.fetch_balance()
        return json.dumps({
            "total_value": str(snap.total_value),
            "available_cash": str(snap.available_cash),
            "unrealized_pnl": str(snap.unrealized_pnl),
            "realized_pnl": str(snap.realized_pnl),
            "return_percent": str(snap.return_percent),
            "timestamp": snap.timestamp.isoformat(),
        })
    finally:
        await exchange.close()


@mcp.tool()
async def list_positions() -> str:
    """List all currently open positions with size / pnl / leverage."""
    exchange = _get_exchange()
    try:
        positions = await exchange.fetch_positions()
        return json.dumps({
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "quantity": str(p.quantity),
                    "entry_price": str(p.entry_price),
                    "current_price": str(p.current_price),
                    "unrealized_pnl": str(p.unrealized_pnl),
                    "leverage": p.leverage,
                    "stop_loss": str(p.stop_loss) if p.stop_loss is not None else None,
                    "cumulative_close_pct": str(p.cumulative_close_pct),
                    "trailing_peak_pnl_pct": str(p.trailing_peak_pnl_pct),
                }
                for p in positions
            ],
            "count": len(positions),
        }, default=str)
    finally:
        await exchange.close()


@mcp.tool()
async def open_orders(symbol: str | None = None) -> str:
    """List live (open / partially filled) exchange orders.

    Args:
        symbol: Optional symbol filter; omit to list all live orders.
    """
    exchange = _get_exchange()
    Symbol = _get_symbol_module()
    try:
        sym = Symbol(value=symbol) if symbol else None
        orders = await exchange.fetch_open_orders(sym)
        return json.dumps({
            "orders": [
                {
                    "id": o.id,
                    "symbol": str(o.symbol),
                    "side": o.side,
                    "status": o.status,
                    "price": str(o.price),
                    "size": str(o.size),
                    "remaining": str(o.remaining),
                    "timestamp": o.timestamp.isoformat(),
                }
                for o in orders
            ],
            "count": len(orders),
        }, default=str)
    finally:
        await exchange.close()


# ---------------------------------------------------------------------------
# Risk tool (pure compute — no exchange needed)
# ---------------------------------------------------------------------------


_VALID_STRATEGIES: frozenset[str] = frozenset({
    "arena-guardian", "arena-steward", "arena-raider", "arena-raider-squad",
    "arena-scalper", "arena-swingsmith", "arena-strider", "arena-rebate-hunter",
    "arena-autopilot", "arena-dual-signal", "arena-tribunal",
})


@mcp.tool()
async def calculate_risk(
    strategy: str,
    max_leverage: int,
    account_equity: str,
    confidence: str,
) -> str:
    """Compute leverage band + max-loss + position-notional budget for a trade.

    Args:
        strategy: Strategy name (e.g. 'arena-guardian', 'arena-autopilot').
        max_leverage: System-wide leverage ceiling (e.g. 25).
        account_equity: Total account equity in USDT (as string).
        confidence: Decision confidence in [0, 1] (as string).
    """
    from omnitrade.domain.enums import StrategyName
    from omnitrade.domain.services.leverage_bands import get_leverage_band

    if strategy not in _VALID_STRATEGIES:
        return json.dumps({"error": f"unknown strategy {strategy!r}", "valid": sorted(_VALID_STRATEGIES)})

    strat_enum = StrategyName(strategy)
    equity = Decimal(account_equity)
    conf = Decimal(confidence)
    min_lev, max_lev = get_leverage_band(strat_enum, max_leverage)
    leverage = round(min_lev + (max_lev - min_lev) * float(conf))
    risk_fraction = conf * Decimal("0.02")
    max_loss_usdt = equity * risk_fraction
    position_notional_usdt = equity * Decimal(leverage) * risk_fraction
    return json.dumps({
        "strategy": strategy,
        "leverage_band": {"min": min_lev, "max": max_lev},
        "suggested_leverage": leverage,
        "max_loss_usdt": str(max_loss_usdt),
        "position_notional_usdt": str(position_notional_usdt),
        "risk_fraction": str(risk_fraction),
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
