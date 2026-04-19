"""Pure-function performance metrics for the backtest result.

No pandas; numpy + stdlib only. Metrics are computed over the equity
curve (list of ``(timestamp, equity_usdt)``) and the realised-trade
list (only ``type == "close"`` entries carry ``pnl``).

Sharpe is annualised with sqrt(252) on daily returns (standard
crypto/equities convention). Max drawdown is a running-max fraction.
Win rate / avg_win / avg_loss / profit_factor are computed over
closed trades with non-null ``pnl``.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Any

from omnitrade.domain.entities import Trade

# Trading days per year for annualisation. Crypto markets are 24/7 but
# daily-bucketed returns convention stays at 252 to match literature.
_TRADING_DAYS_PER_YEAR: int = 252


def _bucket_equity_by_day(
    equity_curve: list[tuple[datetime, Decimal]],
) -> list[float]:
    """Return end-of-day equity values in chronological order.

    When two consecutive samples fall on the same UTC day the later one
    wins — this matches how daily-bar backtests typically sample.
    Single-sample buckets are dropped from the *daily return* series
    because a return needs two consecutive days.
    """
    by_day: dict[str, float] = {}
    order: list[str] = []
    for ts, eq in equity_curve:
        day_key = ts.strftime("%Y-%m-%d")
        if day_key not in by_day:
            order.append(day_key)
        by_day[day_key] = float(eq)
    return [by_day[k] for k in order]


def _sharpe_annualised(daily_returns: list[float]) -> float:
    """Annualised Sharpe ratio (risk-free rate = 0).

    Returns 0.0 when the daily-return series has fewer than two points
    or when the standard deviation is zero (flat equity curve).
    """
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(var)
    if std == 0.0:
        return 0.0
    return (mean / std) * math.sqrt(_TRADING_DAYS_PER_YEAR)


def _max_drawdown_pct(equity_values: list[float]) -> float:
    """Return the worst peak-to-trough drawdown as a percentage (>= 0)."""
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    worst = 0.0
    for v in equity_values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > worst:
                worst = dd
    return worst * 100.0


def compute_metrics(
    equity_curve: list[tuple[datetime, Decimal]],
    trades: list[Trade],
) -> dict[str, Any]:
    """Compute summary performance metrics.

    Args:
        equity_curve: ``[(timestamp, total_equity_usdt), ...]`` sampled
            once per backtest cycle (engine appends after each tick).
        trades: Every executed trade. Only entries with
            ``type == "close"`` AND ``pnl is not None`` count as
            realised outcomes for win-rate / profit-factor math.

    Returns:
        Dict with keys: ``total_return_pct``, ``sharpe_ratio_annualised``,
        ``max_drawdown_pct``, ``win_rate``, ``trade_count``, ``avg_win``,
        ``avg_loss``, ``profit_factor``, ``final_equity``,
        ``initial_equity``.
    """
    if not equity_curve:
        return {
            "initial_equity": 0.0,
            "final_equity": 0.0,
            "total_return_pct": 0.0,
            "sharpe_ratio_annualised": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "trade_count": 0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
        }

    initial_eq = float(equity_curve[0][1])
    final_eq = float(equity_curve[-1][1])
    total_return_pct = 0.0 if initial_eq == 0.0 else (final_eq - initial_eq) / initial_eq * 100.0

    eq_values = [float(eq) for _ts, eq in equity_curve]
    max_dd_pct = _max_drawdown_pct(eq_values)

    daily_eq = _bucket_equity_by_day(equity_curve)
    daily_returns: list[float] = []
    for i in range(1, len(daily_eq)):
        prev = daily_eq[i - 1]
        cur = daily_eq[i]
        if prev != 0.0:
            daily_returns.append((cur - prev) / prev)
    sharpe = _sharpe_annualised(daily_returns)

    closes = [t for t in trades if t.type == "close" and t.pnl is not None]
    wins = [float(t.pnl) for t in closes if t.pnl is not None and t.pnl > Decimal(0)]
    losses = [float(t.pnl) for t in closes if t.pnl is not None and t.pnl <= Decimal(0)]
    trade_count = len(closes)
    win_rate = (len(wins) / trade_count) if trade_count else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    gross_profit = sum(wins)
    gross_loss = -sum(losses)  # positive value
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

    return {
        "initial_equity": initial_eq,
        "final_equity": final_eq,
        "total_return_pct": total_return_pct,
        "sharpe_ratio_annualised": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "win_rate": win_rate,
        "trade_count": trade_count,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
    }


__all__ = ["compute_metrics"]
