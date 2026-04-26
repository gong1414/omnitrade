"""Domain entities — Pydantic models mapping to the 8 DB tables.

No ORM imports. These are plain Python objects; SQLAlchemy mapping lives in Phase 3.
All timestamps are tz-aware datetime; all money amounts use Decimal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

# NOTE: ``list[str]`` for gates_passed is the domain representation; the
# repository layer is responsible for json.dumps/json.loads at the DB boundary.
from pydantic import BaseModel, field_validator

from omnitrade.domain.value_objects import Symbol


class Position(BaseModel):
    """Active futures position — mirrors the `positions` table.

    Three-way state contract fields (cumulative_close_pct, stop_loss,
    trailing_peak_pnl_pct) MUST be updated atomically via apply_partial_close().
    """

    id: int | None = None
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    liquidation_price: Decimal
    unrealized_pnl: Decimal
    leverage: int
    side: str  # "long" | "short"
    profit_target: Decimal | None = None
    stop_loss: Decimal | None = None  # override % threshold (nullable)
    tp_order_id: str | None = None
    sl_order_id: str | None = None
    entry_order_id: str
    opened_at: datetime
    confidence: Decimal | None = None
    risk_usd: Decimal | None = None
    trailing_peak_pnl_pct: Decimal = Decimal("0")  # highest levered pnl% ever observed
    cumulative_close_pct: Decimal = Decimal("0")  # cumulative % closed (0..100)

    model_config = {"frozen": True}

    @field_validator("quantity")
    @classmethod
    def quantity_non_negative(cls, v: Decimal) -> Decimal:
        if v < Decimal(0):
            raise ValueError(f"Position quantity must be >= 0, got {v}")
        return v

    @field_validator("leverage")
    @classmethod
    def leverage_valid(cls, v: int) -> int:
        if not (1 <= v <= 125):
            raise ValueError(f"Leverage must be in [1, 125], got {v}")
        return v

    @field_validator("cumulative_close_pct")
    @classmethod
    def partial_close_valid(cls, v: Decimal) -> Decimal:
        if not (Decimal(0) <= v <= Decimal(100)):
            raise ValueError(f"cumulative_close_pct must be in [0, 100], got {v}")
        return v

    def apply_partial_close(
        self,
        new_pct: Decimal,
        new_sl: Decimal | None,
        new_peak: Decimal,
    ) -> Position:
        """Return a new Position with the three-way state contract fields updated atomically.

        Encoding the atomicity rule: all three fields (cumulative_close_pct,
        stop_loss, trailing_peak_pnl_pct) change together — never individually.
        Phase 3 infrastructure must enforce the atomic SQL UPDATE by consuming
        this function's output as a single transaction.
        """
        return self.model_copy(
            update={
                "cumulative_close_pct": new_pct,
                "stop_loss": new_sl,
                "trailing_peak_pnl_pct": new_peak,
            }
        )


class Trade(BaseModel):
    """Executed trade record — mirrors the `trades` table."""

    id: int | None = None
    order_id: str
    symbol: str
    side: str  # "long" | "short"
    type: str  # "open" | "close"
    price: Decimal
    quantity: Decimal
    leverage: int
    pnl: Decimal | None = None
    fee: Decimal | None = None
    timestamp: datetime
    status: str = "pending"

    model_config = {"frozen": True}


class AccountSnapshot(BaseModel):
    """Account asset snapshot — mirrors the `account_history` table."""

    id: int | None = None
    timestamp: datetime
    total_value: Decimal
    available_cash: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    return_percent: Decimal
    sharpe_ratio: Decimal | None = None

    model_config = {"frozen": True}


class TradingSignal(BaseModel):
    """Market technical indicators snapshot — mirrors the `trading_signals` table."""

    id: int | None = None
    symbol: str
    timestamp: datetime
    price: Decimal
    ema_20: Decimal
    ema_50: Decimal | None = None
    macd: Decimal
    rsi_7: Decimal
    rsi_14: Decimal
    volume: Decimal
    open_interest: Decimal | None = None
    funding_rate: Decimal | None = None
    atr_3: Decimal | None = None
    atr_14: Decimal | None = None

    model_config = {"frozen": True}


class AgentDecision(BaseModel):
    """AI agent decision record — mirrors the `agent_decisions` table.

    correlation_id links to TraceContext for distributed tracing.

    Structured reasoning fields (PR-B1 Step 5): populated when the LLM emits
    a StructuredReason-shaped ``reason`` object.  All six are nullable so that
    legacy rows (pre-Step-5) degrade transparently — DB NULLs map to None.
    DB column ``confidence`` maps to domain field ``structured_confidence``
    (Option A naming: DB retains ``confidence``, repository translates).
    """

    id: int | None = None
    timestamp: datetime
    iteration: int  # 0 for monitor-triggered; >0 for trading-loop cycles
    market_analysis: str  # JSON blob
    decision: str  # human-readable
    actions_taken: str  # JSON array
    account_value: Decimal
    positions_count: int
    symbol: str | None = None  # e.g. "BTC_USDT" — None for hold
    side: str | None = None  # "long" | "short" — None for hold
    correlation_id: str = ""  # TraceContext linkage (persisted in alembic 0005)
    # StructuredReason fields — None for legacy rows
    market_context: str | None = None
    gates_passed: list[str] | None = None  # domain list; repo json.dumps/loads at DB boundary
    invalidation_condition: str | None = None
    plan: dict[str, Any] | None = None  # PlanBlock.model_dump() or None
    structured_confidence: float | None = None  # DB column name: ``confidence``
    output_language: str | None = None  # "zh" | "en" | None
    # Alembic 0005: full StructuredReason.justification (≈1385 chars mean);
    # None for legacy rows predating the audit fix.
    justification: str | None = None

    model_config = {"frozen": True}


class TradingLesson(BaseModel):
    """RAG trading lesson — mirrors the `trading_lessons` table."""

    id: int | None = None
    pattern: str
    action: str
    outcome: str
    lesson: str
    confidence: Decimal = Decimal("0.5")
    hit_count: int = 1
    market_regime: str = "unknown"
    created_at: datetime
    last_validated: datetime | None = None
    archived: bool = False
    embedding: list[float] | None = None

    model_config = {"frozen": True}


class TradeOutcome(BaseModel):
    """Trade result for RAG feedback — mirrors the `trade_outcomes` table."""

    id: int | None = None
    trade_id: str | None = None
    symbol: str
    side: str
    entry_conditions_json: str | None = None
    exit_conditions_json: str | None = None
    pnl_percent: Decimal | None = None
    duration_hours: Decimal | None = None
    lesson_extracted: bool = False
    created_at: datetime

    model_config = {"frozen": True}


class Decision(BaseModel):
    """Agent decision output — produced by the Agno trading agent.

    This is the *DSL* the agent emits; it is distinct from ``AgentDecision``
    (a persisted audit-log row). A ``Decision`` is the structured instruction
    for the outer loop's ``execute_trades`` step. The Agno Agent's
    ``DecisionRecorder`` tools (``agents/tools/decision_schemas.py``)
    construct it from the LLM's tool-call payload.

    The JSON contract is documented in ``agents/prompts/think.py`` alongside
    the user-message template that instructs the LLM to emit this shape.
    """

    action: str  # "open" | "close" | "partial_close" | "hold"
    symbol: str | None = None
    side: str | None = None  # "long" | "short"
    size: Decimal | None = None
    leverage: int | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    confidence: Decimal | None = None
    reasoning: str = ""
    close_percentage: Decimal | None = None  # for partial_close (0..100)
    lessons_applied: list[str] = []
    # StructuredReason fields (Step 4, PR-B1): populated only when the LLM
    # emits ``args["reason"]`` as a dict conforming to StructuredReason schema.
    # Legacy flat-string path leaves all six fields None (backward-compat).
    market_context: str | None = None
    gates_passed: list[str] | None = None  # domain list; repo layer json.dumps to DB
    invalidation_condition: str | None = None
    plan: dict[str, Any] | None = None  # PlanBlock.model_dump() result, or None for hold
    structured_confidence: float | None = None  # StructuredReason.confidence (float, [0,1])
    output_language: Literal["zh", "en"] | None = None
    # Full chain-of-thought justification (StructuredReason.justification).
    # ``reasoning`` stays as the caller-facing short text for backward compat
    # (existing prompts / feedback loops read it); ``justification`` carries
    # the raw long-form CoT for audit + UI consumption.
    justification: str | None = None

    model_config = {"frozen": True}

    @field_validator("action")
    @classmethod
    def action_is_known(cls, v: str) -> str:
        allowed = {"open", "close", "partial_close", "hold"}
        if v not in allowed:
            raise ValueError(f"Decision.action must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("leverage")
    @classmethod
    def leverage_bounds(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 125):
            raise ValueError(f"Decision.leverage must be in [1, 125], got {v}")
        return v

    @field_validator("close_percentage")
    @classmethod
    def close_percentage_bounds(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not (Decimal(0) <= v <= Decimal(100)):
            raise ValueError(f"Decision.close_percentage must be in [0, 100], got {v}")
        return v


class NewsItem(BaseModel):
    """Normalized news headline — the domain view consumed by the agent layer.

    ``infrastructure.news.NewsFetcher`` returns a near-identical shape but
    is an adapter-layer class; this Pydantic model is the pure-domain seam
    so ``agents/`` and ``application/`` stay framework-free.
    """

    source: str
    headline: str
    summary: str
    published_at: datetime
    sentiment: str | None = None

    model_config = {"frozen": True}


class MarketSnapshot(BaseModel):
    """Aggregated per-cycle market observation.

    A thin domain wrapper over the fields the agent's ``think`` node needs.
    Phase 5 will enrich this with technical-indicator series; for now it
    carries the minimum (symbols + ticker prices + account context).

    Phase 8.1: ``multi_tf_ohlcv`` is an optional, additive field populated
    by ``MultiTimeframeFetcher`` via the ``build_think_fn`` enricher.
    Outer key is the symbol string; inner key is the timeframe label
    (e.g. ``"1m"``); value is a list of OHLCV candles. Left ``None``
    when the multi-timeframe pipeline is disabled (rollback parity).

    Phase 8.6 (G-6): ``ws_buffer_hash`` is a transient, in-memory fingerprint
    of the WebSocket ticker buffer captured at ``observe_market`` entry
    when a ``WSClient`` is wired in. It lives ONLY inside ``run_cycle``
    and is NOT persisted to ``agent_decisions.market_analysis``. The
    field stays ``None`` when the WS path is off (``USE_WS_MARKET_DATA
    =false``) or in cassette mode.
    """

    timestamp: datetime
    symbols: list[str]
    tickers: dict[str, Decimal]  # symbol -> last price
    account: AccountSnapshot | None = None
    positions: list[Position] = []
    multi_tf_ohlcv: dict[str, dict[str, list[Any]]] | None = None
    ws_buffer_hash: str | None = None

    model_config = {"frozen": True}


class Order(BaseModel):
    """Open-order snapshot returned by ``ExchangeClient.fetch_open_orders`` et al.

    Distinct from :class:`Trade` (settled execution record) — an ``Order`` is a
    live / historical exchange order whose lifecycle status is one of
    ``open`` | ``filled`` | ``cancelled`` | ``partially_filled``.
    """

    id: str
    symbol: Symbol
    side: Literal["long", "short"]
    status: Literal["open", "filled", "cancelled", "partially_filled"]
    price: Decimal
    size: Decimal
    remaining: Decimal
    timestamp: datetime

    model_config = {"frozen": True}


class SystemConfig(BaseModel):
    """Key/value system configuration — mirrors the `system_config` table."""

    id: int | None = None
    key: str
    value: str
    updated_at: datetime

    model_config = {"frozen": True}

    @field_validator("key")
    @classmethod
    def key_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SystemConfig key must not be empty")
        return v


# Re-export for convenience
__all__ = [
    "AccountSnapshot",
    "AgentDecision",
    "Decision",
    "MarketSnapshot",
    "NewsItem",
    "Order",
    "Position",
    "SystemConfig",
    "Trade",
    "TradeOutcome",
    "TradingLesson",
    "TradingSignal",
]


def _check_field_types() -> dict[str, Any]:
    """Internal: return field metadata for inspection (not public API)."""
    return {
        "Position.fields": list(Position.model_fields.keys()),
        "Trade.fields": list(Trade.model_fields.keys()),
    }
