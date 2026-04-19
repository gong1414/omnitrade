"""add symbol and side columns to agent_decisions

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

So the frontend can show which symbol/side each decision targeted,
without parsing the actions_taken JSON blob. Nullable — hold decisions
have no symbol or side.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.add_column(sa.Column("symbol", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("side", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.drop_column("side")
        batch_op.drop_column("symbol")
