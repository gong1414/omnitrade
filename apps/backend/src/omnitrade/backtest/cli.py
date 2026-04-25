"""Argparse-driven CLI for the backtest harness.

Usage::

    python -m omnitrade.backtest \\
        --symbol BTC_USDT \\
        --timeframe 4h \\
        --start 2026-01-01 \\
        --end 2026-02-01 \\
        --strategy arena-autopilot \\
        --initial-balance 10000 \\
        --use-cache \\
        --output .backtest/runs/

The LLM defaults to ``LiteLLMClient.from_settings(Settings())`` (real
DeepSeek). ``--use-cache`` wraps it with ``CachedLLMClient`` so
identical request bodies replay from disk.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import structlog

from omnitrade.backtest.clock import BacktestClock
from omnitrade.backtest.data_source import HistoricalOHLCV
from omnitrade.backtest.engine import BacktestEngine
from omnitrade.backtest.exchange import BacktestExchange
from omnitrade.backtest.llm_cache import CachedLLMClient
from omnitrade.config import Settings
from omnitrade.domain.protocols import LLMClient
from omnitrade.infrastructure.llm.agno_llm_adapter import AgnoLLMAdapter

logger = structlog.get_logger(__name__)


def _parse_iso(s: str) -> datetime:
    if "T" not in s:
        s = f"{s}T00:00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m omnitrade.backtest",
        description="Run a historical backtest over the trading loop.",
    )
    p.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        default=None,
        help="Symbol to trade (repeatable). Default: BTC_USDT",
    )
    p.add_argument("--timeframe", default="4h", help="Primary timeframe (default 4h)")
    p.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    p.add_argument(
        "--strategy",
        default="arena-autopilot",
        help="Strategy name (default arena-autopilot)",
    )
    p.add_argument(
        "--initial-balance",
        type=float,
        default=10000.0,
        help="Starting balance in USDT (default 10000)",
    )
    p.add_argument(
        "--cycle-bars",
        type=int,
        default=1,
        help="Run one cycle every N bars of the primary timeframe (default 1)",
    )
    p.add_argument(
        "--use-cache",
        action="store_true",
        help="Wrap the LLM client in a sqlite response cache.",
    )
    p.add_argument(
        "--cache-path",
        default=".backtest/llm_cache.db",
        help="Path to the LLM sqlite cache (default .backtest/llm_cache.db)",
    )
    p.add_argument(
        "--ohlcv-cache-path",
        default=".backtest/ohlcv_cache.db",
        help="Path to the OHLCV sqlite cache (default .backtest/ohlcv_cache.db)",
    )
    p.add_argument(
        "--output",
        default=".backtest/runs/",
        help="Directory for the generated markdown report (default .backtest/runs/)",
    )
    return p


def _build_llm(*, use_cache: bool, cache_path: str) -> LLMClient:
    settings = Settings()
    base: LLMClient = AgnoLLMAdapter.from_settings(settings)
    if use_cache:
        return CachedLLMClient(base, cache_path=cache_path, use_cache=True)
    return base


async def _run_async(args: argparse.Namespace) -> int:
    symbols = args.symbols or ["BTC_USDT"]
    start = _parse_iso(args.start)
    end = _parse_iso(args.end)

    # Settings is the ONLY canonical source for the trading strategy + model.
    # We override trading_strategy on a private copy so the CLI flag wins.
    settings = Settings()
    settings = settings.model_copy(update={"trading_strategy": args.strategy})

    data_source = HistoricalOHLCV(cache_path=args.ohlcv_cache_path)
    exchange = BacktestExchange(
        initial_balance_usdt=Decimal(str(args.initial_balance)),
        data_source=data_source,
    )
    clock = BacktestClock(start=start)
    llm = _build_llm(use_cache=args.use_cache, cache_path=args.cache_path)

    engine = BacktestEngine(
        exchange=exchange,
        clock=clock,
        data_source=data_source,
        llm=llm,
        settings=settings,
        symbols=symbols,
        timeframe=args.timeframe,
        start=start,
        end=end,
        cycle_bars=args.cycle_bars,
    )

    logger.info(
        "backtest.cli.start",
        symbols=symbols,
        timeframe=args.timeframe,
        start=start.isoformat(),
        end=end.isoformat(),
        strategy=args.strategy,
    )
    try:
        result = await engine.run()
    finally:
        await data_source.close()
        if isinstance(llm, CachedLLMClient):
            llm.close()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"backtest-{'-'.join(symbols)}-{stamp}.md"
    report_path.write_text(result.to_markdown(), encoding="utf-8")

    print(f"Report written to: {report_path}")  # noqa: T201 — intentional CLI surface
    print(f"Total return: {result.metrics.get('total_return_pct', 0.0):+.2f}%")  # noqa: T201
    print(f"Sharpe:       {result.metrics.get('sharpe_ratio_annualised', 0.0):.2f}")  # noqa: T201
    print(f"Max DD:       {result.metrics.get('max_drawdown_pct', 0.0):.2f}%")  # noqa: T201
    print(f"Trades:       {result.metrics.get('trade_count', 0)}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run_async(args))


__all__ = ["main"]
