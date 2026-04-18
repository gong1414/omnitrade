"""Contract symbol mapping between ccxt unified symbols and Gate/OKX contract IDs.

ccxt unified:  BTC/USDT:USDT  (linear perpetual)
Gate contract: BTC_USDT
OKX contract:  BTC-USDT-SWAP
"""

from __future__ import annotations


def gate_to_ccxt(gate_symbol: str) -> str:
    """Convert Gate contract symbol to ccxt unified perpetual symbol.

    Examples:
        BTC_USDT  ->  BTC/USDT:USDT
        ETH_USDT  ->  ETH/USDT:USDT
    """
    if "_" not in gate_symbol:
        raise ValueError(f"Invalid Gate symbol (expected BASE_QUOTE): {gate_symbol!r}")
    base, quote = gate_symbol.split("_", 1)
    return f"{base}/{quote}:{quote}"


def ccxt_to_gate(ccxt_symbol: str) -> str:
    """Convert ccxt unified perpetual symbol to Gate contract symbol.

    Examples:
        BTC/USDT:USDT  ->  BTC_USDT
        ETH/USDT:USDT  ->  ETH_USDT
    """
    if "/" not in ccxt_symbol:
        raise ValueError(f"Invalid ccxt symbol (expected BASE/QUOTE:SETTLE): {ccxt_symbol!r}")
    base_quote, _settle = ccxt_symbol.split(":", 1)
    base, quote = base_quote.split("/", 1)
    return f"{base}_{quote}"


def okx_to_ccxt(okx_symbol: str) -> str:
    """Convert OKX swap instrument ID to ccxt unified perpetual symbol.

    Examples:
        BTC-USDT-SWAP  ->  BTC/USDT:USDT
    """
    parts = okx_symbol.split("-")
    if len(parts) < 2:
        raise ValueError(f"Invalid OKX symbol: {okx_symbol!r}")
    base = parts[0]
    quote = parts[1]
    return f"{base}/{quote}:{quote}"


def ccxt_to_okx(ccxt_symbol: str) -> str:
    """Convert ccxt unified perpetual symbol to OKX swap instrument ID.

    Examples:
        BTC/USDT:USDT  ->  BTC-USDT-SWAP
    """
    if "/" not in ccxt_symbol:
        raise ValueError(f"Invalid ccxt symbol: {ccxt_symbol!r}")
    base_quote, _settle = ccxt_symbol.split(":", 1)
    base, quote = base_quote.split("/", 1)
    return f"{base}-{quote}-SWAP"


# Canonical internal symbol format used throughout OmniTrade (Gate style: BASE_QUOTE)
def normalize_to_internal(raw: str) -> str:
    """Normalize any symbol format to OmniTrade internal Gate-style format.

    Accepts:
        BTC_USDT            ->  BTC_USDT   (already internal)
        BTC/USDT:USDT       ->  BTC_USDT   (ccxt unified)
        BTC-USDT-SWAP       ->  BTC_USDT   (OKX)
        BTCUSDT             ->  BTCUSDT    (raw, returned as-is)
    """
    if "_" in raw and "/" not in raw and "-" not in raw:
        return raw  # already Gate format
    if ":" in raw:
        return ccxt_to_gate(raw)
    if raw.endswith("-SWAP"):
        return ccxt_to_gate(okx_to_ccxt(raw))
    return raw  # unknown format — return as-is
