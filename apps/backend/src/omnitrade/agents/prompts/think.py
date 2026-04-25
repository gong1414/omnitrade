"""User-message template for the think step.

The think template is the structured view the LangGraph think node feeds
to the LLM: MarketSnapshot + News + Positions -> a Decision JSON.

Phase 8.1 -- ``{market_data_block}`` has two assembly versions:

* ``v1`` (default) renders the pre-8.1 ticker summary and is byte-exact
  with Phase 4.5 cassette replay.
* ``v2`` additionally embeds the ``MarketSnapshot.multi_tf_ohlcv`` block
  under per-TF headings (``### {tf} ({n} candles)``).

The *template itself* is unchanged -- only the caller-supplied
``market_data_block`` content differs. ``format_market_data_block``
below is the single seam that chooses the version.

PR-B2 Phase B rewrote the prose frame into English and appended an
explicit tool-call + output_language trailer so the model always produces a
StructuredReason in the orchestrator's configured language.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

# Per-cycle user prompt. Fields:
#   {iteration}, {current_time}, {minutes_elapsed}, {interval_minutes},
#   {strategy_banner}, {hard_risk_floor}, {tactical_box}, {decision_flow},
#   {market_data_block}, {news_block}, {external_block}, {account_block},
#   {positions_block}, {sharpe_block}, {recent_trades_block},
#   {output_language}
THINK_USER_TEMPLATE = """\
[CYCLE #{iteration}] {current_time} -- elapsed {minutes_elapsed} min, cadence {interval_minutes} min.

{strategy_banner}

{hard_risk_floor}

{tactical_box}

{decision_flow}

[MARKET DATA]
{market_data_block}

[NEWS FEED]
{news_block}

[EXTERNAL SIGNALS]
{external_block}

[ACCOUNT SNAPSHOT]
{account_block}

[OPEN POSITIONS]
{positions_block}

{sharpe_block}

[RECENT TRADES]
{recent_trades_block}

Based on the above, call ONE of: open_position / close_position / partial_close / hold_tool.
The `reason` field MUST be a complete StructuredReason JSON object with all 7 keys.
Reply reasoning (market_context / gates_passed / invalidation_condition / justification fields) in {output_language}. Use the section headers "Market Context" / "Gates Passed" / "Invalidation" / "Plan" / "Confidence" in that language where applicable.
"""

def _format_v1_market_block(tickers: Iterable[tuple[str, str]]) -> str:
    """Pre-8.1 market block: ``"SYMBOL: price / ..."`` summary.

    Extracted so both v1 and v2 share the ticker preamble -- v2 appends
    multi-TF OHLCV blocks after it.
    """
    pairs = [f"{sym}: {price}" for sym, price in tickers]
    return " / ".join(pairs) if pairs else "none"


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
    "format_market_data_block",
]
