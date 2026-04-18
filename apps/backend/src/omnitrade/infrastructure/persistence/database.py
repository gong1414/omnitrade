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


def _make_async_url(url: str) -> str:
    """Convert sync SQLite URL to async (aiosqlite) URL."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
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
    """
    async_url = _make_async_url(database_url)

    sync_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    sync_factory: sessionmaker[Session] = sessionmaker(
        bind=sync_engine, autocommit=False, autoflush=False
    )

    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False},
    )
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
