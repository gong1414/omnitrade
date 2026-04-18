"""Initial schema — 8 tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-17

Tables created (in dependency order):
  system_config, account_history, trading_signals,
  trades, positions, agent_decisions,
  trading_lessons, trade_outcomes

Downgrade drops all 8 in reverse order.

Uses op.create_table() directly (no ORM Base). SQLAlchemy 2.0 ORM models
are introduced later; this migration remains the canonical DDL source and
will NOT be auto-regenerated.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # system_config                                                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # ------------------------------------------------------------------ #
    # account_history                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "account_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_value", sa.Float, nullable=False),
        sa.Column("available_cash", sa.Float, nullable=False),
        sa.Column("unrealized_pnl", sa.Float, nullable=False),
        sa.Column("realized_pnl", sa.Float, nullable=False),
        sa.Column("return_percent", sa.Float, nullable=False),
        sa.Column("sharpe_ratio", sa.Float, nullable=True),
    )
    op.create_index("idx_history_timestamp", "account_history", ["timestamp"])

    # ------------------------------------------------------------------ #
    # trading_signals                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "trading_signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("ema_20", sa.Float, nullable=False),
        sa.Column("ema_50", sa.Float, nullable=True),
        sa.Column("macd", sa.Float, nullable=False),
        sa.Column("rsi_7", sa.Float, nullable=False),
        sa.Column("rsi_14", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("open_interest", sa.Float, nullable=True),
        sa.Column("funding_rate", sa.Float, nullable=True),
        sa.Column("atr_3", sa.Float, nullable=True),
        sa.Column("atr_14", sa.Float, nullable=True),
    )
    op.create_index("idx_signals_timestamp", "trading_signals", ["timestamp"])
    op.create_index("idx_signals_symbol", "trading_signals", ["symbol"])

    # ------------------------------------------------------------------ #
    # trades                                                               #
    # ------------------------------------------------------------------ #
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),    # 'long' | 'short'
        sa.Column("type", sa.Text, nullable=False),    # 'open' | 'close'
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("leverage", sa.Integer, nullable=False),
        sa.Column("pnl", sa.Float, nullable=True),
        sa.Column("fee", sa.Float, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    )
    op.create_index("idx_trades_timestamp", "trades", ["timestamp"])
    op.create_index("idx_trades_symbol", "trades", ["symbol"])

    # ------------------------------------------------------------------ #
    # positions  ← three-way state contract lives here                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.Text, nullable=False, unique=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("current_price", sa.Float, nullable=False),
        sa.Column("liquidation_price", sa.Float, nullable=False),
        sa.Column("unrealized_pnl", sa.Float, nullable=False),
        sa.Column("leverage", sa.Integer, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("profit_target", sa.Float, nullable=True),
        # three-way state contract fields — see domain/services/three_way_state.py
        sa.Column("stop_loss", sa.Float, nullable=True),
        sa.Column("tp_order_id", sa.Text, nullable=True),
        sa.Column("sl_order_id", sa.Text, nullable=True),
        sa.Column("entry_order_id", sa.Text, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("risk_usd", sa.Float, nullable=True),
        sa.Column("peak_pnl_percent", sa.Float, nullable=False, server_default="0"),
        sa.Column("partial_close_percentage", sa.Float, nullable=False, server_default="0"),
    )

    # ------------------------------------------------------------------ #
    # agent_decisions                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False),
        sa.Column("market_analysis", sa.Text, nullable=False),  # JSON blob
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("actions_taken", sa.Text, nullable=False),    # JSON array
        sa.Column("account_value", sa.Float, nullable=False),
        sa.Column("positions_count", sa.Integer, nullable=False),
    )
    op.create_index("idx_decisions_timestamp", "agent_decisions", ["timestamp"])

    # ------------------------------------------------------------------ #
    # trading_lessons (RAG source)                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "trading_lessons",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("lesson", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("market_regime", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean, nullable=False, server_default="0"),
    )
    op.create_index("idx_lessons_regime", "trading_lessons", ["market_regime"])
    op.create_index("idx_lessons_archived", "trading_lessons", ["archived"])

    # ------------------------------------------------------------------ #
    # trade_outcomes (RAG source)                                          #
    # ------------------------------------------------------------------ #
    op.create_table(
        "trade_outcomes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trade_id", sa.Text, nullable=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("entry_conditions_json", sa.Text, nullable=True),
        sa.Column("exit_conditions_json", sa.Text, nullable=True),
        sa.Column("pnl_percent", sa.Float, nullable=True),
        sa.Column("duration_hours", sa.Float, nullable=True),
        sa.Column("lesson_extracted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_outcomes_symbol", "trade_outcomes", ["symbol"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("idx_outcomes_symbol", table_name="trade_outcomes")
    op.drop_table("trade_outcomes")

    op.drop_index("idx_lessons_archived", table_name="trading_lessons")
    op.drop_index("idx_lessons_regime", table_name="trading_lessons")
    op.drop_table("trading_lessons")

    op.drop_index("idx_decisions_timestamp", table_name="agent_decisions")
    op.drop_table("agent_decisions")

    op.drop_table("positions")

    op.drop_index("idx_trades_symbol", table_name="trades")
    op.drop_index("idx_trades_timestamp", table_name="trades")
    op.drop_table("trades")

    op.drop_index("idx_signals_symbol", table_name="trading_signals")
    op.drop_index("idx_signals_timestamp", table_name="trading_signals")
    op.drop_table("trading_signals")

    op.drop_index("idx_history_timestamp", table_name="account_history")
    op.drop_table("account_history")

    op.drop_table("system_config")
