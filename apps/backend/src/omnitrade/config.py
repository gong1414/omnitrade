"""Pydantic Settings v2 — all environment variables for OmniTrade backend.

Variables are grouped by domain:
  TRADING_*     — trading engine configuration
  EXCHANGE_*    — exchange selection + credentials
  LLM_*         — LiteLLM / AI model configuration
  DATASOURCE_*  — external market data sources (toggle + API keys)
  MCP_*         — MCP tool servers
  REBATE_*      — fee rebate accounting
  IP_*          — IP / network configuration (ports)
  OBSERVABILITY_* — logging and tracing

Phase-0 finding resolutions (approved by user):
  - TRADING_STRATEGY default = "arena-autopilot" (follows .env.example, not registry fallback)
  - ACCOUNT_RECORD_INTERVAL_MINUTES default = 1 (follows .env.example, not code fallback of 10)
  - Fee rate (0.0005) will move to config in Phase 3 (noted in HANDOFF)
  - closePositionTool gap will be closed in Phase 4 (noted in HANDOFF)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All OmniTrade configuration, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # TRADING_* — trading engine                                           #
    # ------------------------------------------------------------------ #
    trading_strategy: str = "arena-autopilot"
    """Active strategy name. One of the 11 registered strategies.
    Default follows .env.example (Phase-0 finding #2 resolution).
    """

    trading_interval_minutes: int = 20
    """How often the main AI trading loop fires (minutes)."""

    max_leverage: int = 25
    """Maximum leverage multiplier allowed."""

    default_leverage: int = 5
    """Fallback leverage when the LLM omits it from an open-position tool call."""

    default_position_size: Decimal = Decimal("0.1")
    """Fallback position size (in contracts) when the LLM omits it."""

    max_positions: int = 5
    """Maximum number of concurrent open positions."""

    max_holding_hours: int = 36
    """Force-close positions older than this (hours)."""

    extreme_stop_loss_percent: float = -30.0
    """Hard-floor stop-loss (negative %, e.g. -30 = -30%). Applied before AI."""

    initial_balance_usdt: float = 1000.0
    """Starting balance used for return-percent calculations."""

    account_stop_loss_usdt: float = 50.0
    """Absolute USDT loss that triggers account-level stop."""

    account_take_profit_usdt: float = 20_000.0
    """Absolute USDT profit that triggers account-level take-profit."""

    sync_config_on_startup: bool = True
    """Write Settings values to system_config table on startup."""

    account_record_interval_minutes: int = 1
    """Interval for periodic account-history snapshots (minutes).
    Default follows .env.example (Phase-0 finding #3 resolution).
    """

    # Drawdown risk controls
    account_drawdown_warning_percent: float = 20.0
    account_drawdown_no_new_position_percent: float = 30.0
    account_drawdown_force_close_percent: float = 50.0

    # ------------------------------------------------------------------ #
    # EXCHANGE_* — exchange selection + credentials                        #
    # ------------------------------------------------------------------ #
    exchange: Literal["gate", "okx"] = "gate"

    gate_api_key: SecretStr | None = None
    gate_api_secret: SecretStr | None = None
    gate_use_testnet: bool = True

    okx_api_key: SecretStr | None = None
    okx_api_secret: SecretStr | None = None
    okx_api_passphrase: SecretStr | None = None
    okx_use_testnet: bool = True

    manual_close_password: SecretStr | None = None
    """Pre-shared password for the POST /api/close-position endpoint.
    Empty / unset disables the UI close feature.
    """

    # ------------------------------------------------------------------ #
    # LLM_* — LiteLLM / AI model                                          #
    # ------------------------------------------------------------------ #
    llm_provider: str = "deepseek"
    """LiteLLM provider prefix (e.g. 'deepseek', 'openai', 'openrouter')."""

    llm_api_key: SecretStr | None = None
    """LiteLLM API key (maps to OPENAI_API_KEY in upstream for compat)."""

    llm_base_url: AnyHttpUrl | None = None
    """Optional base URL override for LiteLLM (OpenAI-compat endpoint)."""

    llm_model_name: str = "deepseek/deepseek-v3.2-exp"
    """Full model identifier passed to LiteLLM."""

    deepseek_api_key: SecretStr | None = None
    """Direct DeepSeek API key (alternative to llm_api_key)."""

    # ------------------------------------------------------------------ #
    # DATASOURCE_* — external market data toggles + API keys              #
    # ------------------------------------------------------------------ #
    datasource_crypto_news_enabled: bool = True
    datasource_fear_greed_enabled: bool = True
    datasource_coingecko_enabled: bool = True
    datasource_onchain_enabled: bool = True
    datasource_order_book_enabled: bool = True
    datasource_open_interest_enabled: bool = True
    datasource_coinglass_enabled: bool = True
    datasource_whale_alert_enabled: bool = True
    datasource_lunar_crush_enabled: bool = True

    coinglass_api_key: SecretStr | None = None
    whale_alert_api_key: SecretStr | None = None
    etherscan_api_key: SecretStr | None = None
    lunar_crush_api_key: SecretStr | None = None

    # ------------------------------------------------------------------ #
    # MCP_* — MCP tool servers                                             #
    # ------------------------------------------------------------------ #
    gate_news_mcp_enabled: bool = True
    gate_news_mcp_url: AnyHttpUrl = AnyHttpUrl("https://api.gatemcp.ai/mcp/news")

    openspace_enabled: bool = True
    openspace_mcp_url: AnyHttpUrl = AnyHttpUrl("http://openspace:8080")
    openspace_cloud_enabled: bool = True

    trading_mcp_port: int = 9090

    # ------------------------------------------------------------------ #
    # REBATE_* — fee rebate accounting                                     #
    # ------------------------------------------------------------------ #
    fee_rebate_percent: float = 20.0
    """Percentage of fees returned as rebate (0-100)."""

    # ------------------------------------------------------------------ #
    # IP_* / port configuration                                            #
    # ------------------------------------------------------------------ #
    platform_port: int = 8000
    openspace_dashboard_port: int = 7788

    # ------------------------------------------------------------------ #
    # OBSERVABILITY_* — logging / tracing                                  #
    # ------------------------------------------------------------------ #
    environment: Literal["testnet", "mainnet"] = "testnet"
    log_level: str = "INFO"

    # ------------------------------------------------------------------ #
    # DATABASE                                                             #
    # ------------------------------------------------------------------ #
    database_url: str = "sqlite:///./data/omnitrade.db"

    vector_db_path: str = "./data/trading_lessons.db"
    """Path to the sqlite-vec database file for RAG lesson embeddings."""

    # ------------------------------------------------------------------ #
    # EXCHANGE FEES (Phase-0 finding #9 resolution)                        #
    # ------------------------------------------------------------------ #
    exchange_fee_rate: float = 0.0005
    """Taker fee rate used when ccxt exchange.fees is unavailable (default 0.0005 = 0.05%)."""

    # ------------------------------------------------------------------ #
    # PHASE 8.1 — Multi-timeframe market data                              #
    # ------------------------------------------------------------------ #
    multi_timeframe_enabled: bool = False
    """Rollback kill-switch for the multi-timeframe enrichment pipeline.

    When False, the ``build_think_fn`` composition returns the base
    ``ThinkFn`` unchanged — the v1 path is byte-exact with prior phases
    (cassette replay depends on this).
    """

    ccxt_rate_limit_rps: int = 16
    """Upstream-parity RPS budget for the multi-TF fetcher.

    The ``MultiTimeframeFetcher`` semaphore permit count is
    ``max(ccxt_rate_limit_rps // 2, 8)``.
    """

    prompt_assembly_version: Literal["v1", "v2"] = "v1"
    """Prompt assembly version selector.

    ``v1`` preserves the pre-8.1 ``{market_data_block}`` shape (ticker
    summary) for cassette-replay byte-exactness. ``v2`` emits the
    multi-TF block consuming ``MarketSnapshot.multi_tf_ohlcv``.
    """

    # ------------------------------------------------------------------ #
    # PHASE 8.2 — Indicator pipeline                                       #
    # ------------------------------------------------------------------ #
    indicators_enabled: bool = False
    """Rollback kill-switch for the Phase 8.2 ``SignalService`` pipeline.

    When False, ``trading_loop.run_cycle`` skips the ``record_signals``
    step entirely — the v1 path is byte-exact with prior phases
    (cassette replay depends on this). When True, per-cycle OHLCV is
    reduced to EMA / MACD / RSI / ATR and inserted into the
    ``trading_signals`` table before the LLM think step runs.
    """

    # ------------------------------------------------------------------ #
    # PHASE 8.5b — Strict tool_choice                                      #
    # ------------------------------------------------------------------ #
    strict_tool_calls: bool = True
    """Reject LLM responses without ``tool_calls`` (Phase 8.5b, plan v3).

    When True (default), ``agents/think_node._decision_from_llm_response``
    raises :class:`~omnitrade.agents.think_node.ToolCallRequiredError`
    whenever an upstream LLM reply is missing ``choices[0].message.tool_calls``.
    The minimal-prompt branch (``arena-autopilot`` / ``arena-dual-signal``) already
    forces ``tool_choice="required"``; this flag is the 1-release rollback
    seam (set ``STRICT_TOOL_CALLS=false`` to re-enable a legacy fallback if
    a provider regresses).
    """

    # ------------------------------------------------------------------ #
    # PHASE 8.5a — Multi-agent orchestrator                                #
    # ------------------------------------------------------------------ #
    multi_agent_enabled: bool = False
    """Rollback kill-switch for the Phase 8.5a multi-agent orchestrator.

    When False, ``build_think_fn`` does not register any roster tools and
    the single-agent path preserves prior behavior. When True AND the active strategy is
    ``arena-raider-squad`` or ``arena-tribunal``, the per-strategy
    roster (4 experts or 3 jurors) is registered into ``ToolRegistry`` so
    the main LLM can drive sub-agent calls via ``tool_calls``.
    """

    multi_agent_strict: bool = True
    """Strictness policy for multi-agent sub-agent failures (plan v3 MINOR-7).

    True (default): partial sub-agent failure raises
    ``MultiAgentDegradedError`` and fails the cycle. False: soft-degrade
    — fall through to the single-agent path, log a warning.
    """

    expert_timeout_seconds: int = 15
    """Per-sub-agent LLM timeout budget (plan v3 MAJOR-3).

    Each expert/juror handler wraps its ``llm.complete`` call in
    ``asyncio.wait_for(..., timeout=expert_timeout_seconds)``. Timeout
    raises ``MultiAgentDegradedError``.
    """

    # ------------------------------------------------------------------ #
    # PHASE 8.6 — WebSocket market stream + cassette mutex                 #
    # ------------------------------------------------------------------ #
    use_ws_market_data: bool = False
    """Rollback kill-switch for the Phase 8.6 WebSocket market-data path.

    False (default, rollback-safe): ``observe_market`` reads only via
    the REST ``exchange_observe`` path, and the ``MarketSnapshot.
    ws_buffer_hash`` field stays ``None`` (legacy REST-only snapshot
    shape). True: the monitor wires an ``OKXWebSocketClient`` /
    ``GateWebSocketClient`` into ``run_cycle`` and the per-cycle
    snapshot carries a sha256 fingerprint of the live buffer.
    """

    cassette_mode: bool = False
    """Cassette byte-replay mode (Phase 8.6 CRITICAL-1).

    When True, ``observe_market`` forces the REST path regardless of
    any ``ws_client`` argument, and the monitor refuses to start with
    ``use_ws_market_data=True`` simultaneously. Tests that rely on
    deterministic cassette byte-replay toggle this to True.
    """

    # ------------------------------------------------------------------ #
    # PHASE 8.7 — Scheduler + end-to-end cycle wiring                     #
    # ------------------------------------------------------------------ #
    scheduler_enabled: bool = False
    """Enable the APScheduler-driven trading cycle at app startup.

    Default False keeps the API server read-only (matches pre-8.7 behavior
    used by the autopilot test harness + local dev). When True AND
    ``llm_api_key`` is present, ``main.lifespan`` composes the production
    ``TradingLoopMonitor`` via ``application.composition.build_trading_monitor``
    and registers a recurring ``monitor.tick`` job at
    ``trading_interval_minutes``.
    """

    trading_symbols: list[str] = ["BTC_USDT", "ETH_USDT"]
    """Symbols observed per trading cycle (tickers + positions).

    Passed into ``build_trading_monitor`` so the composition's
    ``exchange_observe`` fn knows which tickers to fetch. Ignored when
    ``scheduler_enabled`` is False.
    """

    # ------------------------------------------------------------------ #
    # PR-D PHASE D2 — Invalidation monitor                                 #
    # ------------------------------------------------------------------ #
    invalidation_check_interval_seconds: int = 60
    """How often ``InvalidationMonitor`` scans OPEN positions and asks the
    LLM whether each position's ``invalidation_condition`` has triggered.

    Independent from ``trading_interval_minutes`` so invalidation firings
    are enforced on their own cadence. Ignored when ``scheduler_enabled``
    is False."""

    # Position monitors (stop-loss, trailing-stop, partial-profit)
    position_monitor_interval_seconds: int = 10
    """How often the stop-loss, trailing-stop, and partial-profit monitors
    scan OPEN positions. Default 10s for responsive protection.
    Ignored when ``scheduler_enabled`` is False."""

    # ------------------------------------------------------------------ #
    # PR-D PHASE D3 — Adaptive learning + daily loss cap                  #
    # ------------------------------------------------------------------ #
    daily_loss_cap_usdt: float = 100.0
    """Absolute USDT loss cap per UTC day. Exceeding triggers force-hold
    on the next cycle.

    The risk-check layer queries ``trades.pnl`` summed since today UTC
    00:00 and, when the total falls below ``-daily_loss_cap_usdt``, the
    LLM's open / close / partial_close action is overridden to ``hold``.
    ``hold`` decisions are always passed through (no-op).
    """


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
