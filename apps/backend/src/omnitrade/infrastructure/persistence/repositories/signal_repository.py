"""SignalRepository — CRUD for the trading_signals table."""

from __future__ import annotations

from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitrade.domain.entities import TradingSignal
from omnitrade.infrastructure.persistence.models import TradingSignalORM
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _orm_to_domain(row: TradingSignalORM) -> TradingSignal:
    return TradingSignal(
        id=row.id,
        symbol=row.symbol,
        timestamp=row.timestamp,
        price=Decimal(str(row.price)),
        ema_20=Decimal(str(row.ema_20)),
        ema_50=Decimal(str(row.ema_50)) if row.ema_50 is not None else None,
        macd=Decimal(str(row.macd)),
        rsi_7=Decimal(str(row.rsi_7)),
        rsi_14=Decimal(str(row.rsi_14)),
        volume=Decimal(str(row.volume)),
        open_interest=Decimal(str(row.open_interest)) if row.open_interest is not None else None,
        funding_rate=Decimal(str(row.funding_rate)) if row.funding_rate is not None else None,
        atr_3=Decimal(str(row.atr_3)) if row.atr_3 is not None else None,
        atr_14=Decimal(str(row.atr_14)) if row.atr_14 is not None else None,
    )


def _domain_to_orm(sig: TradingSignal) -> TradingSignalORM:
    return TradingSignalORM(
        id=sig.id,
        symbol=sig.symbol,
        timestamp=sig.timestamp,
        price=float(sig.price),
        ema_20=float(sig.ema_20),
        ema_50=float(sig.ema_50) if sig.ema_50 is not None else None,
        macd=float(sig.macd),
        rsi_7=float(sig.rsi_7),
        rsi_14=float(sig.rsi_14),
        volume=float(sig.volume),
        open_interest=float(sig.open_interest) if sig.open_interest is not None else None,
        funding_rate=float(sig.funding_rate) if sig.funding_rate is not None else None,
        atr_3=float(sig.atr_3) if sig.atr_3 is not None else None,
        atr_14=float(sig.atr_14) if sig.atr_14 is not None else None,
    )


class SignalRepository:
    """CRUD operations for the trading_signals table."""

    async def get(self, session: AsyncSession, signal_id: int) -> TradingSignal | None:
        with_context(logger).debug("signal_repository.get", signal_id=signal_id)
        result = await session.get(TradingSignalORM, signal_id)
        return _orm_to_domain(result) if result else None

    async def list_by_symbol(
        self, session: AsyncSession, symbol: str, limit: int = 100
    ) -> list[TradingSignal]:
        with_context(logger).debug("signal_repository.list_by_symbol", symbol=symbol)
        stmt = (
            select(TradingSignalORM)
            .where(TradingSignalORM.symbol == symbol)
            .order_by(TradingSignalORM.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [_orm_to_domain(r) for r in result.scalars().all()]

    async def create(self, session: AsyncSession, sig: TradingSignal) -> TradingSignal:
        with_context(logger).info("signal_repository.create", symbol=sig.symbol)
        row = _domain_to_orm(sig)
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return _orm_to_domain(row)
