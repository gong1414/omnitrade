"""SQLAlchemy 2.0 ORM models — mirrors Alembic 0001 schema exactly.

Uses Mapped[...] / mapped_column(...) with DeclarativeBase.
All Float columns match the Alembic migration — no Numeric here
(Alembic 0001 uses sa.Float throughout; ORM must match to pass drift check).
DateTime columns use timezone=True.
Indexes mirror op.create_index() calls in 0001 exactly (same names, same columns).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class TradeORM(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trades_timestamp", "timestamp"),
        Index("idx_trades_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")


class PositionORM(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # unique=True on the column mirrors `unique=True` in op.create_table()
    symbol: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    liquidation_price: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    profit_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sl_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_order_id: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    trailing_peak_pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    cumulative_close_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )


class AccountHistoryORM(Base):
    __tablename__ = "account_history"
    __table_args__ = (Index("idx_history_timestamp", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    available_cash: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    return_percent: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)


class TradingSignalORM(Base):
    __tablename__ = "trading_signals"
    __table_args__ = (
        Index("idx_signals_timestamp", "timestamp"),
        Index("idx_signals_symbol", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    ema_20: Mapped[float] = mapped_column(Float, nullable=False)
    ema_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=False)
    rsi_7: Mapped[float] = mapped_column(Float, nullable=False)
    rsi_14: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    funding_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_3: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_14: Mapped[float | None] = mapped_column(Float, nullable=True)


class AgentDecisionORM(Base):
    __tablename__ = "agent_decisions"
    __table_args__ = (
        Index("idx_decisions_timestamp", "timestamp"),
        Index("idx_decisions_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    market_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    actions_taken: Mapped[str] = mapped_column(Text, nullable=False)
    account_value: Mapped[float] = mapped_column(Float, nullable=False)
    positions_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # StructuredReason fields (PR-B1 Step 2 alembic 0003) — all nullable for legacy compat
    market_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    gates_passed: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    invalidation_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str | None] = mapped_column(Text, nullable=True)
    side: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Alembic 0005 — close FE/BE contract audit gaps.
    # Alembic 0006 — renamed correlation_id → run_id (Agno alignment).
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )


class TradingLessonORM(Base):
    __tablename__ = "trading_lessons"
    __table_args__ = (
        Index("idx_lessons_regime", "market_regime"),
        Index("idx_lessons_archived", "archived"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.5")
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    market_regime: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_validated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")


class TradeOutcomeORM(Base):
    __tablename__ = "trade_outcomes"
    __table_args__ = (Index("idx_outcomes_symbol", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    entry_conditions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_conditions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    lesson_extracted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SystemConfigORM(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )


__all__ = [
    "AccountHistoryORM",
    "AgentDecisionORM",
    "Base",
    "PositionORM",
    "SystemConfigORM",
    "TradeORM",
    "TradeOutcomeORM",
    "TradingLessonORM",
    "TradingSignalORM",
]
