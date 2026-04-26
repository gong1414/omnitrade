"""rename agent_decisions.correlation_id to run_id (T5+T6 collapsed)

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-26

After the Agno cutover (Stages A–E + Phase 4.5), every cycle is now an
Agno ``RunOutput`` carrying a native ``run_id``. The legacy column name
``correlation_id`` was leftover LangGraph naming. This migration renames
the persisted column so the DB matches Agno's identifier.

Reversible: ``downgrade()`` flips the column name back so a rollback to
``0005`` keeps schema parity with the pre-rename ORM.

Index ``idx_decisions_correlation_id`` is renamed to
``idx_decisions_run_id``. SQLite goes through ``op.batch_alter_table``;
Postgres handles ``alter_column``/``drop_index``/``create_index``
natively.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the old index first — both backends require the index name to
    # match a column that still exists, so renaming the column under it
    # without dropping leaves a dangling reference on Postgres.
    op.drop_index("idx_decisions_correlation_id", table_name="agent_decisions")
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.alter_column(
            "correlation_id",
            new_column_name="run_id",
        )
    op.create_index(
        "idx_decisions_run_id",
        "agent_decisions",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_decisions_run_id", table_name="agent_decisions")
    with op.batch_alter_table("agent_decisions") as batch_op:
        batch_op.alter_column(
            "run_id",
            new_column_name="correlation_id",
        )
    op.create_index(
        "idx_decisions_correlation_id",
        "agent_decisions",
        ["correlation_id"],
    )
