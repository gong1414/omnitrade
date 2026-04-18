"""Tests for domain value objects."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from omnitrade.domain.value_objects import Leverage, Money, Percentage, PnL, Price, Symbol

# ── Symbol ──────────────────────────────────────────────────────────────────── #


class TestSymbol:
    def test_valid_symbol_uppercased(self) -> None:
        s = Symbol(value="btc_usdt")
        assert s.value == "BTC_USDT"

    def test_valid_symbol_no_separator(self) -> None:
        s = Symbol(value="ETHUSDT")
        assert s.value == "ETHUSDT"

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Symbol(value="")

    def test_invalid_chars_raises(self) -> None:
        with pytest.raises(ValueError):
            Symbol(value="BTC-USDT")  # hyphen not allowed

    def test_str_returns_value(self) -> None:
        assert str(Symbol(value="SOLUSDT")) == "SOLUSDT"

    def test_equality(self) -> None:
        assert Symbol(value="BTC") == Symbol(value="btc")

    def test_hash(self) -> None:
        s = {Symbol(value="BTC"), Symbol(value="ETH")}
        assert len(s) == 2

    def test_frozen(self) -> None:
        sym = Symbol(value="BTC")
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            sym.value = "ETH"  # type: ignore[misc]


# ── Leverage ─────────────────────────────────────────────────────────────────── #


class TestLeverage:
    def test_valid_leverage(self) -> None:
        lev = Leverage(value=25)
        assert int(lev) == 25

    def test_min_leverage(self) -> None:
        Leverage(value=1)

    def test_max_leverage(self) -> None:
        Leverage(value=125)

    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 125"):
            Leverage(value=0)

    def test_over_max_raises(self) -> None:
        with pytest.raises(ValueError, match="1, 125"):
            Leverage(value=126)

    def test_equality(self) -> None:
        assert Leverage(value=10) == Leverage(value=10)
        assert Leverage(value=10) != Leverage(value=11)

    def test_frozen(self) -> None:
        lev = Leverage(value=10)
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            lev.value = 20  # type: ignore[misc]


# ── Money ─────────────────────────────────────────────────────────────────────── #


class TestMoney:
    def test_add(self) -> None:
        a = Money(amount=Decimal("10"), currency="USDT")
        b = Money(amount=Decimal("5"), currency="USDT")
        assert (a + b).amount == Decimal("15")

    def test_subtract(self) -> None:
        a = Money(amount=Decimal("10"), currency="USDT")
        b = Money(amount=Decimal("3"), currency="USDT")
        result = a - b
        assert result.amount == Decimal("7")

    def test_multiply(self) -> None:
        m = Money(amount=Decimal("100"), currency="USDT")
        result = m * Decimal("0.2")
        assert result.amount == Decimal("20")

    def test_add_different_currency_raises(self) -> None:
        a = Money(amount=Decimal("10"), currency="USDT")
        b = Money(amount=Decimal("5"), currency="BTC")
        with pytest.raises(ValueError, match="different currencies"):
            _ = a + b

    def test_subtract_different_currency_raises(self) -> None:
        a = Money(amount=Decimal("10"), currency="USDT")
        b = Money(amount=Decimal("5"), currency="BTC")
        with pytest.raises(ValueError, match="different currencies"):
            _ = a - b

    def test_decimal_precision(self) -> None:
        a = Money(amount=Decimal("1.0000000001"), currency="USDT")
        b = Money(amount=Decimal("2.0000000002"), currency="USDT")
        result = a + b
        assert result.amount == Decimal("3.0000000003")

    def test_equality(self) -> None:
        a = Money(amount=Decimal("10"), currency="USDT")
        b = Money(amount=Decimal("10"), currency="USDT")
        assert a == b

    def test_frozen(self) -> None:
        m = Money(amount=Decimal("10"), currency="USDT")
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            m.amount = Decimal("20")  # type: ignore[misc]


# ── Percentage ────────────────────────────────────────────────────────────────── #


class TestPercentage:
    def test_as_fraction(self) -> None:
        p = Percentage(value=20.5)
        assert p.as_fraction() == pytest.approx(0.205)

    def test_zero_percent(self) -> None:
        p = Percentage(value=0.0)
        assert p.as_fraction() == 0.0

    def test_hundred_percent(self) -> None:
        p = Percentage(value=100.0)
        assert p.as_fraction() == pytest.approx(1.0)

    def test_equality(self) -> None:
        assert Percentage(value=20.5) == Percentage(value=20.5)

    def test_frozen(self) -> None:
        pct = Percentage(value=10.0)
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            pct.value = 20.0  # type: ignore[misc]


# ── Price ──────────────────────────────────────────────────────────────────────── #


class TestPrice:
    def test_valid_price(self) -> None:
        p = Price(value=Decimal("68000.50"))
        assert p.value == Decimal("68000.50")

    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            Price(value=Decimal("0"))

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            Price(value=Decimal("-1"))

    def test_equality(self) -> None:
        assert Price(value=Decimal("100")) == Price(value=Decimal("100"))
        assert Price(value=Decimal("100")) != Price(value=Decimal("101"))

    def test_frozen(self) -> None:
        p = Price(value=Decimal("100"))
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            p.value = Decimal("200")  # type: ignore[misc]


# ── PnL ───────────────────────────────────────────────────────────────────────── #


class TestPnL:
    def _make_pnl(
        self,
        realized: str = "0",
        unrealized: str = "0",
        fees: str = "0",
        rebate: str = "0",
    ) -> PnL:
        return PnL(
            realized=Money(amount=Decimal(realized), currency="USDT"),
            unrealized=Money(amount=Decimal(unrealized), currency="USDT"),
            fees=Money(amount=Decimal(fees), currency="USDT"),
            rebate=Money(amount=Decimal(rebate), currency="USDT"),
        )

    def test_net_basic(self) -> None:
        pnl = self._make_pnl(realized="100", unrealized="50", fees="5", rebate="1")
        net = pnl.net()
        # 100 + 50 - 5 + 1 = 146
        assert net.amount == Decimal("146")
        assert net.currency == "USDT"

    def test_net_with_loss(self) -> None:
        pnl = self._make_pnl(realized="-20", unrealized="-10", fees="2", rebate="0.4")
        net = pnl.net()
        # -20 + -10 - 2 + 0.4 = -31.6
        assert net.amount == Decimal("-31.6")

    def test_mismatched_currencies_raises(self) -> None:
        with pytest.raises(ValueError, match="same currency"):
            PnL(
                realized=Money(amount=Decimal("0"), currency="USDT"),
                unrealized=Money(amount=Decimal("0"), currency="BTC"),
                fees=Money(amount=Decimal("0"), currency="USDT"),
                rebate=Money(amount=Decimal("0"), currency="USDT"),
            )

    def test_frozen(self) -> None:
        pnl = self._make_pnl()
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            pnl.realized = Money(amount=Decimal("10"), currency="USDT")  # type: ignore[misc]
