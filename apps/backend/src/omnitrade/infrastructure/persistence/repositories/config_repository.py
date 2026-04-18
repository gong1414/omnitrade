"""ConfigRepository — CRUD for the system_config table."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import SystemConfig
from omnitrade.infrastructure.persistence.models import SystemConfigORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: SystemConfigORM) -> SystemConfig:
    return SystemConfig(
        id=row.id,
        key=row.key,
        value=row.value,
        updated_at=row.updated_at,
    )


class ConfigRepository:
    """CRUD operations for the system_config table."""

    async def get(self, session: AsyncSession, key: str) -> SystemConfig | None:
        with_context(logger).debug("config_repository.get", key=key)
        stmt = select(SystemConfigORM).where(SystemConfigORM.key == key)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return _orm_to_domain(row) if row else None

    async def list_all(self, session: AsyncSession) -> list[SystemConfig]:
        with_context(logger).debug("config_repository.list_all")
        result = await session.execute(select(SystemConfigORM))
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def set(self, session: AsyncSession, key: str, value: str) -> SystemConfig:
        """Upsert a configuration key."""
        with_context(logger).info("config_repository.set", key=key)
        stmt = select(SystemConfigORM).where(SystemConfigORM.key == key)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        now = datetime.now(tz=UTC)
        if row is None:
            row = SystemConfigORM(key=key, value=value, updated_at=now)
            session.add(row)
        else:
            row.value = value
            row.updated_at = now
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)

    async def delete(self, session: AsyncSession, key: str) -> None:
        with_context(logger).info("config_repository.delete", key=key)
        stmt = select(SystemConfigORM).where(SystemConfigORM.key == key)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await session.delete(row)
            await session.flush()
