"""enable pgvector extension for the trade-journal RAG layer

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26

T10 — Knowledge / trade-journal RAG via Agno ``Knowledge`` + ``PgVector``.

Agno's :class:`PgVector` stores embeddings in a SQLAlchemy ``Vector``
column (from the ``pgvector`` Python client) which requires the Postgres
``vector`` extension to be enabled. The extension is idempotent — repeat
runs are safe — so we install it unconditionally on Postgres dialects.

SQLite parity
-------------
The test DB and the local-dev SQLite path do NOT support
``CREATE EXTENSION``; the migration is therefore a no-op when the active
dialect is anything other than Postgres. Trade-journal RAG itself is
Postgres-only — the factory in
``omnitrade.agents.knowledge.trade_journal`` returns ``None`` whenever
``settings.agno_postgres_url`` is unset, so SQLite test runs never hit
this path at runtime either.

Image note
----------
The default ``postgres:16-alpine`` image used in ``docker-compose.yml``
does NOT bundle pgvector. To run T10 end-to-end the deployment must
swap to ``pgvector/pgvector:pg16`` (or layer the extension into a
custom image). This migration therefore tolerates the extension-missing
case: if the binary is unavailable Postgres returns
``ERROR: could not open extension control file`` and we surface the
error so the operator knows to upgrade their image. We deliberately do
NOT swallow the error here — silently skipping would let the agent
boot, fail to ingest, and leave RAG quietly broken.

Downgrade is a no-op: dropping the extension would corrupt any other
schema that depends on it (and we do not own its lifecycle here).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Dialect-gated DDL. ``CREATE EXTENSION`` is a Postgres-only
    # statement; SQLite (used by the default unit-test DB and local
    # dev) raises a syntax error when handed it.
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally a no-op. Other schemas (Agno's PgVector tables) may
    # depend on the ``vector`` type; dropping the extension is far more
    # destructive than the value of round-tripping this migration.
    pass
