"""Database engine + session factories.

Two factories:
  - sync_engine / sync_session_factory  — used by Alembic migrations only
  - async_engine / async_session_factory — used by app runtime (FastAPI)

get_session() is an async generator suitable as a FastAPI dependency.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql") or url.startswith("postgres://")


def _make_async_url(url: str) -> str:
    """Convert a sync DB URL to its async-driver equivalent.

    SQLite → ``sqlite+aiosqlite:///``  (legacy default)
    Postgres → ``postgresql+psycopg://...`` (psycopg3 sync+async, Phase 6)

    Phase 6 of the Agno migration: Postgres uses the psycopg3 dialect so a
    single driver covers both Alembic (sync) and the FastAPI runtime
    (async). Agno's PostgresDb uses the same driver, so business + Agno
    sessions can coexist on one connection pool.
    """
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    # Normalize legacy `postgres://` (Heroku-style) → `postgresql://` first.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _make_sync_url(url: str) -> str:
    """Sync URL counterpart of `_make_async_url`. Alembic + admin paths
    use the sync engine, which for Postgres also goes through psycopg3
    so we don't pull a second driver (psycopg2) into the runtime."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def build_engines(
    database_url: str,
) -> tuple[
    object,  # sync engine
    sessionmaker[Session],  # sync session factory
    object,  # async engine
    async_sessionmaker[AsyncSession],  # async session factory
]:
    """Create both sync and async engines from a single database URL.

    Returns (sync_engine, sync_factory, async_engine, async_factory).
    Sync engine is used only for Alembic; async for app runtime.

    Driver selection:
        SQLite → aiosqlite (async) + stdlib sqlite (sync)
        Postgres → psycopg3 (both)
    """
    sync_url = _make_sync_url(database_url)
    async_url = _make_async_url(database_url)

    # SQLite needs `check_same_thread=False` to share the in-memory file
    # across threads; Postgres does not (and rejects unknown kwargs).
    sync_kwargs: dict[str, object] = {}
    if _is_sqlite(sync_url):
        sync_kwargs["connect_args"] = {"check_same_thread": False}

    sync_engine = create_engine(sync_url, **sync_kwargs)
    sync_factory: sessionmaker[Session] = sessionmaker(
        bind=sync_engine, autocommit=False, autoflush=False
    )

    # `check_same_thread` is a SQLite-only connect arg; psycopg rejects it.
    async_kwargs: dict[str, object] = {}
    if _is_sqlite(async_url):
        async_kwargs["connect_args"] = {"check_same_thread": False}

    async_engine = create_async_engine(async_url, **async_kwargs)
    async_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=async_engine, expire_on_commit=False, autoflush=False
    )

    return sync_engine, sync_factory, async_engine, async_factory


# Module-level singletons — initialised by build_infrastructure()
_async_factory: async_sessionmaker[AsyncSession] | None = None


def init_async_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    """Called by build_infrastructure() to wire the module-level factory."""
    global _async_factory
    _async_factory = factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a managed AsyncSession."""
    if _async_factory is None:
        raise RuntimeError("Database not initialised — call init_async_factory() first")
    async with _async_factory() as session:
        yield session
