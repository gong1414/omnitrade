"""Domain value objects — immutable, validated, stdlib + pydantic only."""

from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator


class Symbol(BaseModel):
    """Non-empty uppercase trading symbol, e.g. 'BTC_USDT' or 'BTCUSDT'."""

    value: str

    model_config = {"frozen": True}

    @field_validator("value")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not v:
            raise ValueError("Symbol must not be empty")
        upper = v.upper()
        if not re.match(r"^[A-Z0-9_]+$", upper):
            raise ValueError(f"Symbol must be uppercase alphanumeric (with optional '_'): {v!r}")
        return upper

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Symbol):
            return self.value == other.value
        return NotImplemented


class Leverage(BaseModel):
    """Integer leverage in range [1, 125]."""

    value: int

    model_config = {"frozen": True}

    @field_validator("value")
    @classmethod
    def validate_leverage(cls, v: int) -> int:
        if not (1 <= v <= 125):
            raise ValueError(f"Leverage must be in [1, 125], got {v}")
        return v

    def __int__(self) -> int:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Leverage):
            return self.value == other.value
        return NotImplemented


class Money(BaseModel):
    """Monetary amount with a currency denomination."""

    amount: Decimal
    currency: str = "USDT"

    model_config = {"frozen": True}

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ArithmeticError(
                f"Cannot add Money with different currencies: {self.currency} vs {other.currency}"
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ArithmeticError(
                f"Cannot subtract Money with different currencies: "
                f"{self.currency} vs {other.currency}"
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: object) -> Money:
        if not isinstance(factor, Decimal):
            return NotImplemented
        return Money(amount=self.amount * factor, currency=self.currency)

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self.amount == other.amount and self.currency == other.currency
        return NotImplemented


class Percentage(BaseModel):
    """Percentage stored as-is (e.g. 20.5 means 20.5%)."""

    value: float

    model_config = {"frozen": True}

    def as_fraction(self) -> float:
        """Return the decimal fraction, e.g. 20.5 → 0.205."""
        return self.value / 100.0

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Percentage):
            return self.value == other.value
        return NotImplemented


class Price(BaseModel):
    """Positive price as Decimal."""

    value: Decimal

    model_config = {"frozen": True}

    @field_validator("value")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        if v <= Decimal(0):
            raise ValueError(f"Price must be > 0, got {v}")
        return v

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Price):
            return self.value == other.value
        return NotImplemented


class PnL(BaseModel):
    """Profit and loss breakdown for a position or trade."""

    realized: Money
    unrealized: Money
    fees: Money
    rebate: Money

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def validate_currencies_match(self) -> PnL:
        currencies = {
            self.realized.currency,
            self.unrealized.currency,
            self.fees.currency,
            self.rebate.currency,
        }
        if len(currencies) > 1:
            raise ValueError(f"All PnL components must share the same currency, got: {currencies}")
        return self

    def net(self) -> Money:
        """Return realized + unrealized - fees + rebate."""
        currency = self.realized.currency
        net_amount = (
            self.realized.amount + self.unrealized.amount - self.fees.amount + self.rebate.amount
        )
        return Money(amount=net_amount, currency=currency)
