"""ApiContainer — wires Phase-3 infrastructure into Phase-5 application services.

``create_app()`` constructs one ``ApiContainer`` per app instance and stores
it on ``app.state.api_container`` so request handlers can look up the
services they need via ``api.deps``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from omnitrade.agents.think_node import ToolRegistry
from omnitrade.application.account_service import AccountService
from omnitrade.application.decision_service import DecisionService
from omnitrade.application.events.bus import EventBus
from omnitrade.application.position_manager import PositionManager
from omnitrade.application.rebate.service import RebateService
from omnitrade.application.risk_service import DrawdownThresholds, RiskService
from omnitrade.application.signal_service import SignalService
from omnitrade.config import Settings
from omnitrade.domain.enums import StrategyName
from omnitrade.domain.protocols import ExchangeClient, LLMClient
from omnitrade.infrastructure.market_data.gate_ws import GateWebSocketClient
from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.infrastructure.market_data.okx_ws import OKXWebSocketClient
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache
from omnitrade.infrastructure.market_data.ws_client import WSClient
from omnitrade.infrastructure.persistence.repositories.account_history_repository import (
    AccountHistoryRepository,
)
from omnitrade.infrastructure.persistence.repositories.config_repository import (
    ConfigRepository,
)
from omnitrade.infrastructure.persistence.repositories.decision_repository import (
    DecisionRepository,
)
from omnitrade.infrastructure.persistence.repositories.lesson_repository import (
    LessonRepository,
)
from omnitrade.infrastructure.persistence.repositories.outcome_repository import (
    OutcomeRepository,
)
from omnitrade.infrastructure.mcp.client import MCPClient
from omnitrade.infrastructure.mcp.quality_tracker import ToolQualityTracker
from omnitrade.infrastructure.mcp.registry import MCPRegistry
from omnitrade.infrastructure.vector_store.sqlite_vec_store import SQLiteVecStore
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from omnitrade.infrastructure.persistence.repositories.signal_repository import (
    SignalRepository,
)
from omnitrade.infrastructure.persistence.repositories.trade_repository import TradeRepository
from omnitrade.observability.log_store import LogBuffer


@dataclass
class ApiContainer:
    """Holds every Phase-5 service + the session factory used by API deps."""

    event_bus: EventBus
    session_factory: async_sessionmaker[AsyncSession]
    open_session: Callable[[], Awaitable[AsyncSession]]
    account_service: AccountService
    position_manager: PositionManager
    decision_service: DecisionService
    rebate_service: RebateService
    risk_service: RiskService
    position_repo: PositionRepository
    account_history_repo: AccountHistoryRepository
    decision_repo: DecisionRepository
    trade_repo: TradeRepository
    config_repo: ConfigRepository
    lesson_repo: LessonRepository
    outcome_repo: OutcomeRepository
    mcp_registry: MCPRegistry
    tool_quality: ToolQualityTracker
    # Phase 8.3 additions (additive only — no existing service changes).
    exchange: ExchangeClient
    log_buffer: LogBuffer
    # Phase 8.1 additions (multi-TF market data; fetcher idle when
    # ``settings.multi_timeframe_enabled`` is False).
    multi_tf_fetcher: MultiTimeframeFetcher
    # Phase 8.2 additions (indicator pipeline; service idle when
    # ``settings.indicators_enabled`` is False).
    signal_service: SignalService
    # Phase 8.5a additions (multi-agent orchestrator; roster tools are
    # registered into ``tool_registry`` at startup only when
    # ``settings.multi_agent_enabled`` is True AND the active strategy is
    # one of the two multi-agent strategies).
    tool_registry: ToolRegistry
    # Phase 8.6 additions (WebSocket ticker stream; ``None`` when
    # ``settings.use_ws_market_data`` is False — rollback-safe default).
    ws_client: WSClient | None = None
    vec_store: SQLiteVecStore | None = None


def build_api_container(
    *,
    settings: Settings,
    exchange: ExchangeClient,
    session_factory: async_sessionmaker[AsyncSession],
    llm: LLMClient | None = None,
) -> ApiContainer:
    """Construct an ``ApiContainer`` from an already-built infrastructure stack."""
    event_bus = EventBus()

    async def open_session() -> AsyncSession:
        return session_factory()

    position_repo = PositionRepository()
    trade_repo = TradeRepository()
    account_history_repo = AccountHistoryRepository()
    decision_repo = DecisionRepository()
    config_repo = ConfigRepository()
    lesson_repo = LessonRepository()
    outcome_repo = OutcomeRepository()

    mcp_registry = MCPRegistry()
    tool_quality = ToolQualityTracker()

    vec_store = SQLiteVecStore(settings.vector_db_path)

    position_manager = PositionManager(
        exchange=exchange,
        position_repo=position_repo,
        trade_repo=trade_repo,
        session_factory=open_session,
        event_bus=event_bus,
    )
    account_service = AccountService(
        exchange=exchange,
        history_repo=account_history_repo,
        position_repo=position_repo,
        session_factory=open_session,
        event_bus=event_bus,
        initial_balance=Decimal(str(settings.initial_balance_usdt)),
    )
    decision_service = DecisionService(
        repo=decision_repo,
        session_factory=open_session,
        event_bus=event_bus,
    )
    rebate_service = RebateService(
        trade_repo=trade_repo,
        session_factory=open_session,
        fee_rebate_percent=Decimal(str(settings.fee_rebate_percent)),
    )
    risk_service = RiskService(
        DrawdownThresholds(
            warn_percent=Decimal(str(settings.account_drawdown_warning_percent)),
            block_open_percent=Decimal(str(settings.account_drawdown_no_new_position_percent)),
            force_close_percent=Decimal(str(settings.account_drawdown_force_close_percent)),
        )
    )

    # Phase 8.3: shared LogBuffer so /api/logs and structlog sidecar agree.
    log_buffer = LogBuffer()

    # Phase 8.6: optional WS ticker client. Constructed eagerly only when
    # the kill-switch is on; ``start()`` is NOT called here — the app
    # startup hook is responsible for that so tests can inject a stub.
    ws_client: WSClient | None = None
    if settings.use_ws_market_data:
        if settings.exchange == "okx":
            ws_client = OKXWebSocketClient()
        else:
            ws_client = GateWebSocketClient()

    # Phase 8.1: multi-TF fetcher (idle when multi_timeframe_enabled=False).
    multi_tf_cache: InMemoryTTLCache[list[list[float]]] = InMemoryTTLCache()
    multi_tf_fetcher = MultiTimeframeFetcher(
        exchange=exchange,
        cache=multi_tf_cache,
        rate_limit_rps=settings.ccxt_rate_limit_rps,
        ws_client=ws_client,
    )

    # Phase 8.2: indicator compute + persist (idle when indicators_enabled=False).
    signal_repo = SignalRepository()
    signal_service = SignalService(
        repo=signal_repo,
        session_factory=open_session,
    )

    # Phase 8.5a: build the ToolRegistry and — only when the kill-switch is
    # on AND the active strategy is multi-agent — register the strategy's
    # roster. The single-agent path leaves the registry empty (or
    # pre-populated by other phases that hook in later).
    tool_registry = ToolRegistry()
    if settings.multi_agent_enabled and llm is not None:
        active_strategy: StrategyName | None
        try:
            active_strategy = StrategyName(settings.trading_strategy)
        except ValueError:
            active_strategy = None  # unknown strategy — skip roster registration
        if active_strategy in (
            StrategyName.AGGRESSIVE_TEAM,
            StrategyName.MULTI_AGENT_CONSENSUS,
        ):
            from omnitrade.application.multi_agent.roster import roster_for_strategy

            # active_strategy is narrowed by the membership check above but
            # mypy doesn't propagate Optional narrowing through ``in``; the
            # explicit cast keeps ``--strict`` happy.
            assert active_strategy is not None
            for tool in roster_for_strategy(
                active_strategy, llm=llm, settings=settings
            ):

                def _make_handler(
                    bound_tool: Any,
                ) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
                    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
                        result = await bound_tool.ainvoke(args)
                        if isinstance(result, dict):
                            return result
                        return {"result": result}

                    return _handler

                tool_registry.register(tool.name, _make_handler(tool))

    return ApiContainer(
        event_bus=event_bus,
        session_factory=session_factory,
        open_session=open_session,
        account_service=account_service,
        position_manager=position_manager,
        decision_service=decision_service,
        rebate_service=rebate_service,
        risk_service=risk_service,
        position_repo=position_repo,
        account_history_repo=account_history_repo,
        decision_repo=decision_repo,
        trade_repo=trade_repo,
        config_repo=config_repo,
        lesson_repo=lesson_repo,
        outcome_repo=outcome_repo,
        mcp_registry=mcp_registry,
        tool_quality=tool_quality,
        exchange=exchange,
        log_buffer=log_buffer,
        multi_tf_fetcher=multi_tf_fetcher,
        signal_service=signal_service,
        tool_registry=tool_registry,
        ws_client=ws_client,
        vec_store=vec_store,
    )


__all__ = ["ApiContainer", "build_api_container"]
