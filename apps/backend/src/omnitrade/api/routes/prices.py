"""GET /api/prices — batched ticker snapshots with a 5s cache.

The cache lives at module scope so every request against the same
worker shares it; ``symbols`` order is preserved in the response so a
UI keyed by column position stays stable.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from omnitrade.api.deps import get_exchange
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Symbol

router = APIRouter(tags=["prices"])

_MAX_SYMBOLS = 10
_CACHE_TTL_SECONDS = 5.0

# symbol -> (expires_at_monotonic, payload dict)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


def _parse_symbols(raw: str) -> list[str]:
    items = [s.strip() for s in raw.split(",") if s.strip()]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


async def _fetch_ticker_cached(
    exchange: ExchangeClient, symbol: str, now: float
) -> dict[str, Any]:
    """Return cached ticker or fetch fresh; always a small ``{last,bid,ask}`` dict."""
    async with _CACHE_LOCK:
        hit = _CACHE.get(symbol)
        if hit is not None and hit[0] > now:
            return hit[1]
    # Miss: go to exchange. Outside the lock so concurrent symbols don't serialise.
    try:
        raw = await exchange.fetch_ticker(Symbol(value=symbol))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"fetch_ticker failed for {symbol}: {exc}",
        ) from exc
    payload = {
        "last": raw.get("last"),
        "bid": raw.get("bid"),
        "ask": raw.get("ask"),
    }
    async with _CACHE_LOCK:
        _CACHE[symbol] = (now + _CACHE_TTL_SECONDS, payload)
    return payload


@router.get("/prices")
async def get_prices(
    symbols: str = Query(description="Comma-separated symbols, e.g. BTC_USDT,ETH_USDT"),
    exchange: ExchangeClient = Depends(get_exchange),
) -> dict[str, Any]:
    """Return the latest ticker for each symbol (max 10 per call)."""
    parsed = _parse_symbols(symbols)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symbols must not be empty",
        )
    if len(parsed) > _MAX_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"symbols must be <= {_MAX_SYMBOLS}",
        )

    now = time.monotonic()
    # Fan out in parallel — one gather call keeps p95 tight for 10 symbols.
    tickers = await asyncio.gather(
        *[_fetch_ticker_cached(exchange, s, now) for s in parsed]
    )
    return dict(zip(parsed, tickers, strict=True))


def _clear_cache_for_tests() -> None:
    """Test-only hook: clear the module-scope cache between tests."""
    _CACHE.clear()


__all__ = ["router"]
