"""Unit tests for ``application.composition.build_trading_monitor``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from omnitrade.api.container import build_api_container
from omnitrade.application.composition import (
    _build_market_block,
    _build_tool_schemas,
    build_trading_monitor,
)
from omnitrade.config import Settings
from omnitrade.domain.entities import AccountSnapshot, MarketSnapshot
from tests.application._fakes import (
    FakeExchange,
    build_sqlite_session_factory,
    make_trade,
)

# ---------------------------------------------------------------------------
# Fixtures / doubles.
# ---------------------------------------------------------------------------


class _StubLLM:
    """Minimal ``LLMClient`` that returns a canned tool-call response."""

    def __init__(self) -> None:
        self.complete_calls: list[dict[str, Any]] = []

    async def complete(  # type: ignore[no-untyped-def]
        self,
        messages,
        model,
        temperature=0.7,
        tools=None,
        tool_choice=None,
    ):
        self.complete_calls.append(
            {
                "model": model,
                "temperature": temperature,
                "n_messages": len(messages),
                "n_tools": len(tools or []),
                "tool_choice": tool_choice,
            }
        )
        tool_args = {
            "symbol": "BTC_USDT",
            "side": "long",
            "size": 1,
            "leverage": 5,
            "reason": {
                "market_context": (
                    "BTC_USDT in strong 1H bull trend, EMA20>50>200, RSI 65, "
                    "volume +40%. Clean directional bias across 1H and 4H TF."
                ),
                "gates_passed": [
                    "EMA alignment bullish across 1H/4H",
                    "RSI 65 (healthy not exhausted)",
                    "Volume confirmation +40% vs 20SMA",
                ],
                "invalidation_condition": (
                    "Close below recent swing low 73100 on 1H close"
                ),
                "plan": {
                    "entry": 75820,
                    "stop_loss": 73100,
                    "take_profit_1": 77500,
                    "take_profit_2": 79000,
                    "position_size_percent": 10,
                    "holding_timeframe": "4H to 1D",
                },
                "justification": (
                    "Textbook bull alignment with momentum confirmation. Risk "
                    "reward 1:2.5 from current price to TP1. Funding neutral, "
                    "OI expanding supports the move. Entering with conviction "
                    "at current levels, stop below structural support keeps "
                    "risk within account tolerance."
                ),
                "confidence": 0.75,
                "output_language": "en",
            },
        }
        return {
            "model": model,
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "open_position",
                                    "arguments": json.dumps(tool_args),
                                }
                            }
                        ]
                    }
                }
            ],
        }


# ---------------------------------------------------------------------------
# Tool schema sanity test.
# ---------------------------------------------------------------------------


def test_build_tool_schemas_has_four_tools_with_reason_field() -> None:
    tools = _build_tool_schemas()
    assert [t["function"]["name"] for t in tools] == [
        "open_position",
        "close_position",
        "partial_close",
        "hold_tool",
    ]
    for tool in tools:
        props = tool["function"]["parameters"]["properties"]
        assert "reason" in props, f"{tool['function']['name']} missing reason"
    # hold_tool is LAST (Pre-Mortem #4 M1 — ordering counters hold-bias).
    assert tools[-1]["function"]["name"] == "hold_tool"


# ---------------------------------------------------------------------------
# End-to-end tick test — build_trading_monitor + one cycle.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_trading_monitor_runs_one_cycle_and_records_structured_decision() -> None:
    """build_trading_monitor wires a ThinkFn+ExecuteFn that, when ticked once,
    persists an AgentDecision with structured fields populated.
    """
    factory, open_session = await build_sqlite_session_factory()
    balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    fake_exchange = FakeExchange(
        balance=balance,
        positions=[],
        place_order_trade=make_trade(order_id="open-1", ttype="open"),
        close_trade=make_trade(order_id="close-1", ttype="close"),
    )

    settings = Settings(
        environment="testnet",
        trading_strategy="arena-autopilot",
        trading_interval_minutes=20,
        trading_symbols=["BTC_USDT", "ETH_USDT"],
        llm_model_name="deepseek/deepseek-chat",
    )
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]
    container.account_service._session_factory = open_session  # type: ignore[attr-defined]
    container.decision_service._session_factory = open_session  # type: ignore[attr-defined]
    container.position_manager._session_factory = open_session  # type: ignore[attr-defined]

    llm = _StubLLM()
    monitor = build_trading_monitor(container, settings, llm)  # type: ignore[arg-type]

    await monitor.tick()

    # LLM was invoked with tools + required tool_choice for arena-autopilot.
    assert len(llm.complete_calls) == 1
    call = llm.complete_calls[0]
    assert call["model"] == "deepseek/deepseek-chat"
    assert call["n_tools"] == 4
    assert call["tool_choice"] == "required"

    # Exchange place_order was called with the parsed open decision.
    assert len(fake_exchange.place_order_calls) == 1
    placed = fake_exchange.place_order_calls[0]
    assert placed["side"] == "long"
    assert placed["leverage"] == 5

    # DecisionService persisted a row — read it back.
    rows = await container.decision_service.list_recent(limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row.decision == "open"
    assert row.positions_count == 0
    assert row.market_context is not None
    assert len(row.market_context) >= 50
    assert row.gates_passed and len(row.gates_passed) >= 3
    assert row.invalidation_condition is not None
    assert row.plan is not None
    assert row.plan.get("entry") == 75820
    assert row.structured_confidence == pytest.approx(0.75)
    assert row.output_language == "en"


# ---------------------------------------------------------------------------
# PR-D Phase D1 — market block enrichment.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_market_block_emits_indicator_table() -> None:
    """The rich market block contains the indicator table header + data rows."""
    factory, open_session = await build_sqlite_session_factory()
    balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    fake_exchange = FakeExchange(balance=balance, positions=[])
    settings = Settings(
        environment="testnet",
        trading_strategy="arena-autopilot",
        trading_symbols=["BTC_USDT", "ETH_USDT"],
    )
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT", "ETH_USDT"],
        tickers={"BTC_USDT": Decimal("100"), "ETH_USDT": Decimal("100")},
        account=balance,
        positions=[],
    )

    block = await _build_market_block(container, market)

    # Header + at least one data row per symbol.
    assert "15m EMA20/50/200" in block
    assert "15m RSI14" in block
    assert "Volx" in block
    assert "BTC_USDT" in block
    assert "ETH_USDT" in block
    # The recent-closes trailer is appended after the table.
    assert "Recent 15m closes" in block


@pytest.mark.asyncio
async def test_build_market_block_falls_back_when_no_symbols() -> None:
    """Empty ticker + symbols set → legacy (no data) string, no crash."""
    factory, open_session = await build_sqlite_session_factory()
    fake_exchange = FakeExchange(balance=None, positions=[])
    settings = Settings(environment="testnet", trading_symbols=[])
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=[],
        tickers={},
        positions=[],
    )

    block = await _build_market_block(container, market)
    assert block == "(no data)"


@pytest.mark.asyncio
async def test_build_market_block_degrades_on_fetcher_exception() -> None:
    """When the multi-TF fetcher raises, fall back to the ticker summary."""
    factory, open_session = await build_sqlite_session_factory()
    balance = AccountSnapshot(
        timestamp=datetime.now(tz=UTC),
        total_value=Decimal("1000"),
        available_cash=Decimal("900"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        return_percent=Decimal("0"),
    )
    fake_exchange = FakeExchange(balance=balance, positions=[])
    settings = Settings(
        environment="testnet",
        trading_symbols=["BTC_USDT"],
    )
    container = build_api_container(
        settings=settings,
        exchange=fake_exchange,  # type: ignore[arg-type]
        session_factory=factory,
    )
    container.open_session = open_session  # type: ignore[assignment]

    async def _boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("network went poof")

    container.multi_tf_fetcher.fetch_ohlcv_multi_tf = _boom  # type: ignore[method-assign]

    market = MarketSnapshot(
        timestamp=datetime.now(tz=UTC),
        symbols=["BTC_USDT"],
        tickers={"BTC_USDT": Decimal("100")},
        account=balance,
        positions=[],
    )

    block = await _build_market_block(container, market)
    # Legacy ticker format: "BTC_USDT: 100".
    assert "BTC_USDT: 100" in block
    # Not the indicator header.
    assert "EMA20/50/200" not in block
