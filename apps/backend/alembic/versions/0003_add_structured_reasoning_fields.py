"""add structured reasoning fields to agent_decisions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19

Phase-9 Prompt Audit Modernization (PR-B1) — extend agent_decisions with
6 nullable columns to carry Alpha Arena-style structured reasoning:
market_context, gates_passed, invalidation_condition, plan (JSON),
confidence, output_language. All nullable + no server_default so the
upgrade is non-destructive and legacy rows stay readable.

SQLite batch_alter_table used because SQLite doesn't support ADD COLUMN
with some constraints natively. render_as_batch=True already in env.py.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.add_column(sa.Column("market_context", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("gates_passed", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("invalidation_condition", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("plan", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("output_language", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.drop_column("output_language")
        batch_op.drop_column("confidence")
        batch_op.drop_column("plan")
        batch_op.drop_column("invalidation_condition")
        batch_op.drop_column("gates_passed")
        batch_op.drop_column("market_context")
