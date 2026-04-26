"""Tests for domain entities — round-trip serialization and invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from omnitrade.domain.entities import (
    AccountSnapshot,
    AgentDecision,
    Position,
    SystemConfig,
    Trade,
    TradeOutcome,
    TradingLesson,
    TradingSignal,
)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# ── Position ──────────────────────────────────────────────────────────────────── #


class TestPosition:
    def _make(self, **kwargs: object) -> Position:
        defaults: dict[str, object] = {
            "symbol": "BTCUSDT",
            "quantity": Decimal("1"),
            "entry_price": Decimal("68000"),
            "current_price": Decimal("69000"),
            "liquidation_price": Decimal("50000"),
            "unrealized_pnl": Decimal("1000"),
            "leverage": 10,
            "side": "long",
            "entry_order_id": "order-001",
            "opened_at": _utcnow(),
        }
        defaults.update(kwargs)
        return Position(**defaults)  # type: ignore[arg-type]

    def test_round_trip(self) -> None:
        pos = self._make()
        data = pos.model_dump()
        pos2 = Position(**data)
        assert pos2 == pos

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            self._make(quantity=Decimal("-1"))

    def test_invalid_leverage_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 125"):
            self._make(leverage=0)

    def test_invalid_partial_close_raises(self) -> None:
        with pytest.raises(ValueError, match="0, 100"):
            self._make(cumulative_close_pct=Decimal("101"))

    def test_frozen(self) -> None:
        pos = self._make()
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            pos.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_apply_partial_close_returns_new_instance(self) -> None:
        pos = self._make()
        updated = pos.apply_partial_close(
            new_pct=Decimal("30"),
            new_sl=Decimal("2"),
            new_peak=Decimal("8"),
        )
        # Must be a new object
        assert updated is not pos
        assert updated.cumulative_close_pct == Decimal("30")
        assert updated.stop_loss == Decimal("2")
        assert updated.trailing_peak_pnl_pct == Decimal("8")

    def test_apply_partial_close_only_three_fields_change(self) -> None:
        pos = self._make(quantity=Decimal("5"), leverage=20)
        updated = pos.apply_partial_close(
            new_pct=Decimal("30"),
            new_sl=Decimal("3"),
            new_peak=Decimal("10"),
        )
        # Other fields unchanged
        assert updated.quantity == pos.quantity
        assert updated.leverage == pos.leverage
        assert updated.symbol == pos.symbol
        assert updated.entry_order_id == pos.entry_order_id


# ── Trade ─────────────────────────────────────────────────────────────────────── #


class TestTrade:
    def _make(self, **kwargs: object) -> Trade:
        defaults: dict[str, object] = {
            "order_id": "ord-001",
            "symbol": "BTCUSDT",
            "side": "long",
            "type": "open",
            "price": Decimal("68000"),
            "quantity": Decimal("0.1"),
            "leverage": 10,
            "timestamp": _utcnow(),
        }
        defaults.update(kwargs)
        return Trade(**defaults)  # type: ignore[arg-type]

    def test_round_trip(self) -> None:
        t = self._make()
        data = t.model_dump()
        t2 = Trade(**data)
        assert t2 == t

    def test_pnl_optional(self) -> None:
        t = self._make(type="open")
        assert t.pnl is None

    def test_close_trade_with_pnl(self) -> None:
        t = self._make(type="close", pnl=Decimal("50"), fee=Decimal("1.5"))
        assert t.pnl == Decimal("50")
        assert t.fee == Decimal("1.5")

    def test_frozen(self) -> None:
        t = self._make()
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            t.symbol = "ETHUSDT"  # type: ignore[misc]


# ── AccountSnapshot ───────────────────────────────────────────────────────────── #


class TestAccountSnapshot:
    def test_round_trip(self) -> None:
        snap = AccountSnapshot(
            timestamp=_utcnow(),
            total_value=Decimal("10000"),
            available_cash=Decimal("5000"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("200"),
            return_percent=Decimal("7.0"),
        )
        data = snap.model_dump()
        snap2 = AccountSnapshot(**data)
        assert snap2.total_value == snap.total_value


# ── TradingSignal ────────────────────────────────────────────────────────────── #


class TestTradingSignal:
    def test_round_trip(self) -> None:
        sig = TradingSignal(
            symbol="BTCUSDT",
            timestamp=_utcnow(),
            price=Decimal("68000"),
            ema_20=Decimal("67000"),
            macd=Decimal("0.5"),
            rsi_7=Decimal("55"),
            rsi_14=Decimal("52"),
            volume=Decimal("1500"),
        )
        data = sig.model_dump()
        sig2 = TradingSignal(**data)
        assert sig2.rsi_7 == sig.rsi_7


# ── AgentDecision ─────────────────────────────────────────────────────────────── #


class TestAgentDecision:
    def test_run_id_default_empty(self) -> None:
        d = AgentDecision(
            timestamp=_utcnow(),
            iteration=1,
            market_analysis="{}",
            decision="hold",
            actions_taken="[]",
            account_value=Decimal("10000"),
            positions_count=0,
        )
        assert d.run_id == ""

    def test_run_id_set(self) -> None:
        d = AgentDecision(
            timestamp=_utcnow(),
            iteration=1,
            market_analysis="{}",
            decision="hold",
            actions_taken="[]",
            account_value=Decimal("10000"),
            positions_count=0,
            run_id="run-abc-123",
        )
        assert d.run_id == "run-abc-123"


# ── TradingLesson ─────────────────────────────────────────────────────────────── #


class TestTradingLesson:
    def test_embedding_optional(self) -> None:
        lesson = TradingLesson(
            pattern="bullish divergence",
            action="long",
            outcome="profit",
            lesson="buy on divergence",
            created_at=_utcnow(),
        )
        assert lesson.embedding is None

    def test_embedding_stored(self) -> None:
        lesson = TradingLesson(
            pattern="p",
            action="a",
            outcome="o",
            lesson="l",
            created_at=_utcnow(),
            embedding=[0.1, 0.2, 0.3],
        )
        assert lesson.embedding == [0.1, 0.2, 0.3]


# ── TradeOutcome ─────────────────────────────────────────────────────────────── #


class TestTradeOutcome:
    def test_round_trip(self) -> None:
        outcome = TradeOutcome(
            symbol="BTCUSDT",
            side="long",
            pnl_percent=Decimal("5.5"),
            duration_hours=Decimal("2.5"),
            created_at=_utcnow(),
        )
        data = outcome.model_dump()
        outcome2 = TradeOutcome(**data)
        assert outcome2.pnl_percent == outcome.pnl_percent


# ── SystemConfig ──────────────────────────────────────────────────────────────── #


class TestSystemConfig:
    def test_valid_config(self) -> None:
        cfg = SystemConfig(key="peak_balance", value="12345.67", updated_at=_utcnow())
        assert cfg.key == "peak_balance"

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            SystemConfig(key="  ", value="v", updated_at=_utcnow())
