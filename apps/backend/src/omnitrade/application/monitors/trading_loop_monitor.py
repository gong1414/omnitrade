"""TradingLoopMonitor — wraps ``trading_loop.run_cycle`` at ``TRADING_INTERVAL_MINUTES``.

Owns nothing of its own — it just calls ``run_cycle`` with injected step
functions and records the resulting decision via ``DecisionService``.

Phase 8.6 (CRITICAL-1 + MAJOR-5): the monitor is the single enforcement
point for the cassette ↔ WebSocket mutual-exclusion rule. ``__init__``
raises ``RuntimeError`` if both ``use_ws_market_data`` and
``cassette_mode`` are simultaneously true. The assertion lives here —
NOT in ``decision_service.py`` — because the monitor is the startup
seam that owns the run-cycle lifecycle. The WS→cycle contract is
documented in detail in ``application/trading_loop.observe_market``.
"""

from __future__ import annotations

import json
from decimal import Decimal

import structlog

from omnitrade.application.decision_service import DecisionService
from omnitrade.application.monitors.clock import ClockProtocol, SystemClock
from omnitrade.application.trading_loop import (
    ExchangeObserveFn,
    ExecuteFn,
    NewsGatherFn,
    ReflectFn,
    RiskCheckFn,
    ThinkFn,
    run_cycle,
)
from omnitrade.infrastructure.market_data.ws_client import WSClient
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


class TradingLoopMonitor:
    """Periodic tick wrapping the outer trading loop.

    Args:
        ws_client: Optional WebSocket ticker source. When supplied AND
            ``use_ws_market_data`` is True, ``observe_market`` takes a
            snapshot of the WS buffer at cycle entry and attaches
            ``ws_buffer_hash`` to the ``MarketSnapshot`` (G-6 transient
            field). When ``cassette_mode`` is True the WS path is
            ignored; the startup assertion below refuses to run with
            both flags true simultaneously (CRITICAL-1).
        use_ws_market_data: Mirrors ``settings.use_ws_market_data``.
        cassette_mode: Mirrors ``settings.cassette_mode``; forces REST.
    """

    def __init__(
        self,
        *,
        interval_minutes: int,
        exchange_observe: ExchangeObserveFn,
        news_gather: NewsGatherFn,
        think_fn: ThinkFn,
        risk_check: RiskCheckFn,
        execute_fn: ExecuteFn,
        reflect_fn: ReflectFn,
        decision_service: DecisionService,
        clock: ClockProtocol | None = None,
        ws_client: WSClient | None = None,
        use_ws_market_data: bool = False,
        cassette_mode: bool = False,
    ) -> None:
        # CRITICAL-1: refuse to start with both flags simultaneously true.
        # The assertion lives here (monitor) rather than in
        # decision_service.py so the failure surfaces at the startup
        # seam, before the first cycle runs.
        if use_ws_market_data and cassette_mode:
            raise RuntimeError(
                "Cannot enable both USE_WS_MARKET_DATA and CASSETTE_MODE — "
                "WS live stream and cassette byte-replay are mutually exclusive "
                "(Phase 8.6 CRITICAL-1)."
            )
        self._interval_minutes = interval_minutes
        self._exchange_observe = exchange_observe
        self._news_gather = news_gather
        self._think_fn = think_fn
        self._risk_check = risk_check
        self._execute_fn = execute_fn
        self._reflect_fn = reflect_fn
        self._decision_service = decision_service
        self._clock = clock or SystemClock()
        self._iteration = 0
        self._ws_client: WSClient | None = ws_client if use_ws_market_data else None
        self._cassette_mode = cassette_mode

    @property
    def interval_seconds(self) -> float:
        return float(self._interval_minutes * 60)

    async def tick(self) -> None:
        """Drive a single ``run_cycle`` + persist the decision."""
        self._iteration += 1
        with_context(logger).info(
            "trading_loop_monitor.tick",
            iteration=self._iteration,
        )
        outcome = await run_cycle(
            exchange_observe=self._exchange_observe,
            news_gather=self._news_gather,
            think_fn=self._think_fn,
            risk_check=self._risk_check,
            execute_fn=self._execute_fn,
            reflect_fn=self._reflect_fn,
            ws_client=self._ws_client,
            cassette_mode=self._cassette_mode,
        )
        actions_json = json.dumps(
            [
                {
                    "order_id": t.order_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "type": t.type,
                    "quantity": str(t.quantity),
                }
                for t in outcome.trades
            ]
        )
        market_summary = json.dumps(
            {
                "symbols": outcome.market.symbols,
                "news_count": len(outcome.news),
                "positions_count": len(outcome.market.positions),
            }
        )
        account_value = (
            outcome.market.account.total_value if outcome.market.account is not None else Decimal(0)
        )
        decision = outcome.decision
        await self._decision_service.record(
            iteration=self._iteration,
            decision_text=decision.action,
            market_analysis=market_summary,
            actions_taken=actions_json,
            account_value=account_value,
            positions_count=len(outcome.market.positions),
            timestamp=self._clock.now(),
            symbol=decision.symbol,
            side=decision.side,
            # PR-B1/B2 — propagate StructuredReason fields so
            # /api/v1/decisions can surface them to the UI. None-safe:
            # the legacy (flat-string) path leaves every field at None.
            market_context=decision.market_context,
            gates_passed=decision.gates_passed,
            invalidation_condition=decision.invalidation_condition,
            plan=decision.plan,
            structured_confidence=(
                float(decision.structured_confidence)
                if decision.structured_confidence is not None
                else None
            ),
            output_language=decision.output_language,
            justification=decision.justification,
        )


__all__ = ["TradingLoopMonitor"]
