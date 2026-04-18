"""Alembic environment — supports both online (normal) and offline (SQL script) migrations.

Reads DATABASE_URL from OmniTrade Settings so that `alembic upgrade head`
works without a separate alembic.ini edit when running via `uv run`.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make src/ importable from the alembic/ directory
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _backend_dir)
sys.path.insert(0, os.path.join(_backend_dir, "src"))

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from Settings if DATABASE_URL is set in env
try:
    from omnitrade.config import get_settings

    _db_url = get_settings().database_url
    config.set_main_option("sqlalchemy.url", _db_url)
except Exception:  # noqa: BLE001 — tolerate import errors during `alembic revision`
    pass

# Phase 3: set target_metadata to Base for autogenerate drift detection.
try:
    from omnitrade.infrastructure.persistence.models import Base as OrmBase
    target_metadata = OrmBase.metadata
except Exception:  # noqa: BLE001
    target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to the database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
