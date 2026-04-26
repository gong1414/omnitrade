"""Agno-backed ``ThinkFn`` factory for the backtest engine.

Mirrors :mod:`omnitrade.agents.trading_agent.build_agno_think_fn` but
without the production dependencies the backtest cannot satisfy:

  * **No MCP bridge** — historical backtests have no live news / orderbook
    server to query. Decision quality drops a notch but stays reproducible.
  * **No DB-backed sessions** — each cycle builds a fresh Agent. Cross-cycle
    history would require a Postgres schema we don't want the backtest to
    depend on.
  * **No `recent_trades_block`** — the legacy DB lookup is replaced with an
    in-memory shim that surfaces the engine's own trade list.

The think_fn produced here is a drop-in for
:class:`omnitrade.backtest.engine.ThinkFn`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from omnitrade.config import Settings

from agno.agent import Agent

from omnitrade.agents.tools.decision_schemas import (
    DecisionRecorder,
    build_decision_tools,
)
from omnitrade.agents.trading_agent import _resolve_deepseek
from omnitrade.application.composition import (
    _render_market_block,
    _render_think_messages,
)
from omnitrade.domain.entities import Decision, MarketSnapshot, NewsItem
from omnitrade.domain.enums import StrategyName

logger = structlog.get_logger(__name__)


ThinkFn = Callable[[MarketSnapshot, list[NewsItem]], Awaitable[Decision]]


_NO_RECENT_TRADES = "Recent cycles: no prior decisions yet."


async def _stub_market_block(_container: Any, market: MarketSnapshot) -> str:
    """Backtest market block: ticker-only (no multi-TF indicator fetch).

    The production composition layer fetches 15m/1h/4h OHLCV via the
    MultiTFFetcher, but in a backtest we already advanced the
    ``BacktestExchange`` to the current bar and don't want to round-trip
    Binance again per cycle. Surface the legacy ticker block — it carries
    the close price for every observed symbol.
    """
    return _render_market_block(market)


async def _stub_recent_trades(_container: Any) -> str:
    """Backtest feedback block: stubbed — no decisions DB available."""
    return _NO_RECENT_TRADES


def build_backtest_think_fn(
    settings: Settings,
    *,
    strategy: StrategyName | None = None,
) -> ThinkFn:
    """Return a ``think_fn`` backed by an Agno Agent (no MCP, no DB).

    Args:
        settings: Settings instance (provides API keys + model id).
        strategy: Override the configured ``trading_strategy``. ``None``
            falls back to ``StrategyName(settings.trading_strategy)`` with
            ``AI_AUTONOMOUS`` as the safety net.
    """
    if strategy is None:
        try:
            strategy = StrategyName(settings.trading_strategy)
        except ValueError:
            strategy = StrategyName.AI_AUTONOMOUS

    async def think_fn(market: MarketSnapshot, news: list[NewsItem]) -> Decision:
        positions = list(market.positions)
        market_block = await _stub_market_block(None, market)
        recent_trades_block = await _stub_recent_trades(None)
        messages = _render_think_messages(
            strategy=strategy,
            market=market,
            news=news,
            positions=positions,
            settings=settings,
            iteration=0,
            minutes_elapsed=0,
            market_data_block=market_block,
            recent_trades_block=recent_trades_block,
        )
        system_prompt = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        user_prompt = next(
            (m["content"] for m in messages if m.get("role") == "user"), ""
        )

        recorder = DecisionRecorder()
        decision_tools = build_decision_tools(recorder)

        agent = Agent(
            model=_resolve_deepseek(settings),
            instructions=system_prompt,
            tools=list(decision_tools),
            telemetry=False,
        )

        try:
            run_result = await agent.arun(user_prompt)
        except Exception as exc:  # noqa: BLE001 — backtest must keep going
            logger.error("backtest_think.run_failed", error=str(exc))
            return Decision(
                action="hold",
                reasoning=f"agno_agent_run_failed: {exc!r}",
            )

        if recorder.decision is not None:
            return recorder.decision

        text = str(getattr(run_result, "content", "") or "")[:512]
        logger.warning(
            "backtest_think.no_decision_tool_fired",
            run_text_head=text[:120],
        )
        return Decision(
            action="hold",
            reasoning=text or "agno_agent: no decision tool fired (defaulting to hold)",
        )

    return think_fn


__all__ = ["ThinkFn", "build_backtest_think_fn"]
