"""User-message template for the think step.

The think template is the structured view the LangGraph think node feeds
to the LLM: MarketSnapshot + News + Positions → a Decision JSON.

Phase 8.1 — ``{market_data_block}`` has two assembly versions:

* ``v1`` (default) renders the pre-8.1 ticker summary and is byte-exact
  with Phase 4.5 cassette replay.
* ``v2`` additionally embeds the ``MarketSnapshot.multi_tf_ohlcv`` block
  under per-TF headings (``### {tf} ({n} candles)``).

The *template itself* is unchanged — only the caller-supplied
``market_data_block`` content differs. ``format_market_data_block``
below is the single seam that chooses the version.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

# Per-cycle user prompt. Fields:
#   {iteration}, {current_time}, {minutes_elapsed}, {interval_minutes},
#   {strategy_banner}, {hard_risk_floor}, {tactical_box}, {decision_flow},
#   {market_data_block}, {news_block}, {external_block}, {account_block},
#   {positions_block}, {sharpe_block}, {recent_trades_block}
THINK_USER_TEMPLATE = """\
【交易周期 #{iteration}】{current_time} 已运行 {minutes_elapsed} 分钟，执行周期 {interval_minutes} 分钟

{strategy_banner}

{hard_risk_floor}

{tactical_box}

{decision_flow}

【市场数据】
{market_data_block}

【消息面】
{news_block}

【外部数据】
{external_block}

【账户信息】
{account_block}

【当前持仓】
{positions_block}

{sharpe_block}

【近期交易】
{recent_trades_block}

请根据上述信息，按 JSON 格式输出决策：{{"action": "open|close|partial_close|hold", ...}}
"""

think_user_template: HumanMessagePromptTemplate = HumanMessagePromptTemplate.from_template(
    THINK_USER_TEMPLATE
)


def build_think_prompt() -> ChatPromptTemplate:
    """Return a ``ChatPromptTemplate`` with only the user message attached.

    Combine this with a system template via ``ChatPromptTemplate.from_messages``
    at wiring time so each strategy picks the correct system branch.
    """
    return ChatPromptTemplate.from_messages([think_user_template])


def _format_v1_market_block(tickers: Iterable[tuple[str, str]]) -> str:
    """Pre-8.1 market block: ``"SYMBOL: price / ..."`` summary.

    Extracted so both v1 and v2 share the ticker preamble — v2 appends
    multi-TF OHLCV blocks after it.
    """
    pairs = [f"{sym}: {price}" for sym, price in tickers]
    return " / ".join(pairs) if pairs else "无"


def _format_multi_tf_block(
    multi_tf_ohlcv: dict[str, dict[str, list[Any]]] | None,
) -> str:
    """Render ``MarketSnapshot.multi_tf_ohlcv`` as human-readable sub-sections.

    Each symbol emits a ``## {symbol}`` header followed by one
    ``### {tf} ({n} candles)`` table per timeframe. Empty / None input
    returns an empty string so v1 cassettes stay unaffected when the
    multi-TF feature flag is disabled.
    """
    if not multi_tf_ohlcv:
        return ""
    lines: list[str] = []
    for symbol, tf_map in multi_tf_ohlcv.items():
        lines.append(f"## {symbol}")
        for tf, candles in tf_map.items():
            n = len(candles) if candles is not None else 0
            lines.append(f"### {tf} ({n} candles)")
            lines.append("ts,open,high,low,close,volume")
            for candle in candles or []:
                # Candle shape = [timestamp_ms, open, high, low, close, volume]
                row = ",".join(str(x) for x in candle)
                lines.append(row)
            lines.append("")
    return "\n".join(lines).rstrip()


def format_market_data_block(
    *,
    tickers: Iterable[tuple[str, str]],
    prompt_assembly_version: Literal["v1", "v2"] = "v1",
    multi_tf_ohlcv: dict[str, dict[str, list[Any]]] | None = None,
) -> str:
    """Render the ``{market_data_block}`` contents for the think prompt.

    Args:
        tickers: Iterable of ``(symbol, price_str)`` pairs for the v1 preamble.
        prompt_assembly_version: ``"v1"`` preserves byte-exact replay with
            Phase 4.5 cassettes; ``"v2"`` appends the multi-TF block.
        multi_tf_ohlcv: Optional ``MarketSnapshot.multi_tf_ohlcv`` payload;
            ignored when ``prompt_assembly_version == "v1"`` OR the payload
            is falsy.

    Returns:
        A ready-to-interpolate string; callers pass it into
        ``THINK_USER_TEMPLATE.format(market_data_block=...)``.
    """
    v1_block = _format_v1_market_block(tickers)
    if prompt_assembly_version == "v1":
        return v1_block
    multi_tf_block = _format_multi_tf_block(multi_tf_ohlcv)
    if not multi_tf_block:
        return v1_block
    return f"{v1_block}\n\n{multi_tf_block}"


__all__ = [
    "THINK_USER_TEMPLATE",
    "build_think_prompt",
    "format_market_data_block",
    "think_user_template",
]
