"""Infrastructure layer — DB, exchange adapters, LLM, vector store, scheduler, news.

build_infrastructure(settings) -> InfrastructureContainer is the single entry point
for the application layer. Phase 5 will depend on this container.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from omnitrade.config import Settings
from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange
from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient
from omnitrade.infrastructure.news.news_fetcher import NewsFetcher
from omnitrade.infrastructure.persistence.database import build_engines, init_async_factory
from omnitrade.infrastructure.scheduling.scheduler import OmniScheduler
from omnitrade.infrastructure.vector_store.sqlite_vec_store import SQLiteVecStore


@dataclass
class InfrastructureContainer:
    """Holds all infrastructure adapter instances.

    Phase 5 application layer receives this container via dependency injection.
    """

    exchange: CCXTExchange
    llm: LiteLLMClient
    vector_store: SQLiteVecStore
    scheduler: OmniScheduler
    news: NewsFetcher
    session_factory: async_sessionmaker[AsyncSession]


def build_infrastructure(settings: Settings) -> InfrastructureContainer:
    """Factory: construct all infrastructure adapters from Settings.

    Args:
        settings: An omnitrade.config.Settings instance.

    Returns:
        InfrastructureContainer with all adapters wired and ready.
    """
    # ── Persistence ────────────────────────────────────────────────────── #
    _sync_engine, _sync_factory, _async_engine, async_factory = build_engines(settings.database_url)
    init_async_factory(async_factory)

    # ── Exchange ───────────────────────────────────────────────────────── #
    if settings.exchange == "gate":
        api_key = settings.gate_api_key.get_secret_value() if settings.gate_api_key else ""
        api_secret = settings.gate_api_secret.get_secret_value() if settings.gate_api_secret else ""
        exchange = CCXTExchange(
            exchange_id="gate",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.gate_use_testnet,
        )
    else:
        api_key = settings.okx_api_key.get_secret_value() if settings.okx_api_key else ""
        api_secret = settings.okx_api_secret.get_secret_value() if settings.okx_api_secret else ""
        passphrase = (
            settings.okx_api_passphrase.get_secret_value() if settings.okx_api_passphrase else None
        )
        exchange = CCXTExchange(
            exchange_id="okx",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.okx_use_testnet,
            passphrase=passphrase,
        )

    # ── LLM ────────────────────────────────────────────────────────────── #
    llm = LiteLLMClient.from_settings(settings)

    # ── Vector store ───────────────────────────────────────────────────── #
    vector_db_path = getattr(settings, "vector_db_path", "./data/trading_lessons.db")
    vector_store = SQLiteVecStore(db_path=vector_db_path)

    # ── Scheduler ──────────────────────────────────────────────────────── #
    scheduler = OmniScheduler(
        trading_interval_minutes=settings.trading_interval_minutes,
        account_record_interval_minutes=settings.account_record_interval_minutes,
    )

    # ── News ───────────────────────────────────────────────────────────── #
    news = NewsFetcher(mcp_url=str(settings.gate_news_mcp_url))

    return InfrastructureContainer(
        exchange=exchange,
        llm=llm,
        vector_store=vector_store,
        scheduler=scheduler,
        news=news,
        session_factory=async_factory,
    )
