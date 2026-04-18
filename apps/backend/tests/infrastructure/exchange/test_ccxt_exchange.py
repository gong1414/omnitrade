"""Exchange adapter tests — golden JSON contract tests + error handling.

Protocol compliance: isinstance(adapter, ExchangeClient) is True.
Golden fixtures are parsed into domain entities without drift.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omnitrade.domain.entities import AccountSnapshot, Position, Trade
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.domain.value_objects import Leverage, Symbol
from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange
from omnitrade.infrastructure.exchange.contract_mapping import (
    ccxt_to_gate,
    ccxt_to_okx,
    gate_to_ccxt,
    normalize_to_internal,
    okx_to_ccxt,
)

_FIXTURES = (
    Path(__file__).parent.parent.parent.parent
    / "src/omnitrade/infrastructure/exchange/golden_fixtures"
)


def _load(name: str) -> Any:
    return json.loads((_FIXTURES / name).read_text())


# ── Contract mapping unit tests ────────────────────────────────────────────


def test_gate_to_ccxt_btc() -> None:
    assert gate_to_ccxt("BTC_USDT") == "BTC/USDT:USDT"


def test_gate_to_ccxt_eth() -> None:
    assert gate_to_ccxt("ETH_USDT") == "ETH/USDT:USDT"


def test_ccxt_to_gate_btc() -> None:
    assert ccxt_to_gate("BTC/USDT:USDT") == "BTC_USDT"


def test_ccxt_to_gate_eth() -> None:
    assert ccxt_to_gate("ETH/USDT:USDT") == "ETH_USDT"


def test_okx_to_ccxt() -> None:
    assert okx_to_ccxt("BTC-USDT-SWAP") == "BTC/USDT:USDT"


def test_ccxt_to_okx() -> None:
    assert ccxt_to_okx("BTC/USDT:USDT") == "BTC-USDT-SWAP"


def test_normalize_gate_passthrough() -> None:
    assert normalize_to_internal("BTC_USDT") == "BTC_USDT"


def test_normalize_ccxt_unified() -> None:
    assert normalize_to_internal("BTC/USDT:USDT") == "BTC_USDT"


def test_normalize_okx_swap() -> None:
    assert normalize_to_internal("BTC-USDT-SWAP") == "BTC_USDT"


def test_gate_to_ccxt_invalid() -> None:
    with pytest.raises(ValueError):
        gate_to_ccxt("BTCUSDT")  # no underscore


# ── Protocol compliance ────────────────────────────────────────────────────


def test_ccxt_exchange_implements_protocol() -> None:
    """CCXTExchange must satisfy isinstance(x, ExchangeClient)."""
    with patch("omnitrade.infrastructure.exchange.ccxt_exchange.ccxt_async") as mock_ccxt:
        mock_exchange = MagicMock()
        mock_ccxt.gateio.return_value = mock_exchange
        adapter = CCXTExchange(
            exchange_id="gate",
            api_key="key",
            api_secret="secret",
            testnet=True,
        )
    assert isinstance(adapter, ExchangeClient)


# ── Golden fixture contract tests ─────────────────────────────────────────


def test_golden_ticker_fields_present() -> None:
    """Golden ticker JSON has required normalized fields."""
    ticker = _load("gate_ticker.json")
    assert "symbol" in ticker
    assert "last" in ticker or "close" in ticker
    assert "high" in ticker
    assert "low" in ticker
    assert "baseVolume" in ticker


def test_golden_balance_fields_present() -> None:
    """Golden balance JSON parses without KeyError."""
    balance = _load("gate_balance.json")
    total_usdt = balance.get("total", {}).get("USDT", 0)
    free_usdt = balance.get("free", {}).get("USDT", 0)
    assert float(total_usdt) > 0
    assert float(free_usdt) > 0


def test_golden_positions_parse_to_domain() -> None:
    """Golden positions JSON maps to Position domain entities."""
    raw_positions = _load("gate_positions.json")
    assert len(raw_positions) >= 1
    pos = raw_positions[0]
    # Validate key fields exist and are parseable
    assert pos["symbol"] == "BTC/USDT:USDT"
    assert float(pos["contracts"]) > 0
    assert pos["side"] in ("long", "short")
    entry = float(pos["entryPrice"])
    mark = float(pos["markPrice"])
    leverage = int(pos["leverage"])
    assert entry > 0
    assert mark > 0
    assert 1 <= leverage <= 125


def test_golden_ohlcv_shape() -> None:
    """Golden OHLCV has correct [ts, o, h, l, c, v] shape."""
    ohlcv = _load("gate_ohlcv.json")
    assert len(ohlcv) >= 1
    for candle in ohlcv:
        assert len(candle) == 6
        _ts, _open, high, low, _close, vol = candle
        assert high >= low
        assert vol >= 0


# ── Adapter method tests with mocked ccxt ─────────────────────────────────


@pytest.fixture()
def mock_exchange() -> MagicMock:
    m = MagicMock()
    m.fees = {"trading": {"taker": 0.0005}}
    m.set_sandbox_mode = MagicMock()
    m.close = AsyncMock()
    return m


@pytest.fixture()
def adapter(mock_exchange: MagicMock) -> CCXTExchange:
    with patch("omnitrade.infrastructure.exchange.ccxt_exchange.ccxt_async") as mock_ccxt:
        mock_ccxt.gateio.return_value = mock_exchange
        ex = CCXTExchange(
            exchange_id="gate",
            api_key="key",
            api_secret="secret",
            testnet=True,
        )
    ex._exchange = mock_exchange
    return ex


async def test_fetch_balance_returns_account_snapshot(
    adapter: CCXTExchange, mock_exchange: MagicMock
) -> None:
    balance_fixture = _load("gate_balance.json")
    mock_exchange.fetch_balance = AsyncMock(return_value=balance_fixture)
    result = await adapter.fetch_balance()
    assert isinstance(result, AccountSnapshot)
    assert result.total_value == Decimal("10000")
    assert result.available_cash == Decimal("8500")


async def test_fetch_positions_returns_position_list(
    adapter: CCXTExchange, mock_exchange: MagicMock
) -> None:
    positions_fixture = _load("gate_positions.json")
    mock_exchange.fetch_positions = AsyncMock(return_value=positions_fixture)
    result = await adapter.fetch_positions()
    assert isinstance(result, list)
    assert len(result) == 1
    pos = result[0]
    assert isinstance(pos, Position)
    assert pos.symbol == "BTC_USDT"
    assert pos.side == "long"
    assert pos.leverage == 10


async def test_fetch_ticker_returns_dict(adapter: CCXTExchange, mock_exchange: MagicMock) -> None:
    ticker_fixture = _load("gate_ticker.json")
    mock_exchange.fetch_ticker = AsyncMock(return_value=ticker_fixture)
    result = await adapter.fetch_ticker(Symbol(value="BTC_USDT"))
    assert isinstance(result, dict)
    assert "last" in result or "close" in result


async def test_fetch_ohlcv_returns_nested_list(
    adapter: CCXTExchange, mock_exchange: MagicMock
) -> None:
    ohlcv_fixture = _load("gate_ohlcv.json")
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=ohlcv_fixture)
    result = await adapter.fetch_ohlcv(Symbol(value="BTC_USDT"), "1h", 3)
    assert isinstance(result, list)
    assert all(isinstance(c, list) for c in result)


async def test_place_order_returns_trade(adapter: CCXTExchange, mock_exchange: MagicMock) -> None:
    mock_exchange.set_leverage = AsyncMock()
    mock_exchange.create_order = AsyncMock(
        return_value={
            "id": "ord-abc",
            "price": 64000.0,
            "average": 64000.0,
            "status": "closed",
        }
    )
    trade = await adapter.place_order(
        symbol=Symbol(value="BTC_USDT"),
        side="long",
        size=Decimal("0.1"),
        leverage=Leverage(value=10),
    )
    assert isinstance(trade, Trade)
    assert trade.type == "open"
    assert trade.order_id == "ord-abc"


async def test_rate_limit_error_propagates(adapter: CCXTExchange, mock_exchange: MagicMock) -> None:
    """RateLimitError must NOT be swallowed — Phase 5 applies backoff."""
    import ccxt

    mock_exchange.fetch_balance = AsyncMock(side_effect=ccxt.RateLimitExceeded("rate limit"))
    with pytest.raises(ccxt.RateLimitExceeded):
        await adapter.fetch_balance()


async def test_network_error_propagates(adapter: CCXTExchange, mock_exchange: MagicMock) -> None:
    """NetworkError must NOT be swallowed."""
    import ccxt

    mock_exchange.fetch_positions = AsyncMock(side_effect=ccxt.NetworkError("network"))
    with pytest.raises(ccxt.NetworkError):
        await adapter.fetch_positions()
