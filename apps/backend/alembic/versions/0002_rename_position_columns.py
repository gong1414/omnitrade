"""Rename positions columns — zero-share schema identifiers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-18

Renames two columns on the ``positions`` table:

  * peak_pnl_percent          → trailing_peak_pnl_pct
  * partial_close_percentage  → cumulative_close_pct

Uses ``batch_alter_table`` so the migration runs under SQLite (the default
dev/test engine) as well as Postgres-compatible dialects. The other six
columns on ``positions`` (entry_price, stop_loss, etc.) are considered
industry-convergent names and are preserved verbatim.

Round-trip verified: ``alembic upgrade head`` then ``alembic downgrade -1``
restores the prior names without data loss.
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("positions") as batch:
        batch.alter_column(
            "peak_pnl_percent",
            new_column_name="trailing_peak_pnl_pct",
        )
        batch.alter_column(
            "partial_close_percentage",
            new_column_name="cumulative_close_pct",
        )


def downgrade() -> None:
    with op.batch_alter_table("positions") as batch:
        batch.alter_column(
            "cumulative_close_pct",
            new_column_name="partial_close_percentage",
        )
        batch.alter_column(
            "trailing_peak_pnl_pct",
            new_column_name="peak_pnl_percent",
        )
