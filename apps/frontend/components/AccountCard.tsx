"use client";

import { useAccount } from "@/hooks/useAccount";
import { fmtNum, fmtPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";

// Drawdown thresholds must mirror backend allow-listed config keys:
//   account_drawdown_warning_percent   → tone "warn"
//   account_drawdown_no_new_position_percent → tone "warn" (block-new)
//   account_drawdown_force_close_percent → tone "danger" (liquidate)
const DRAWDOWN_WARN = 5;
const DRAWDOWN_BLOCK = 10;
const DRAWDOWN_LIQUIDATE = 20;

function drawdownTone(pct: number): { tone: "success" | "warn" | "danger"; label: string } {
  if (pct >= DRAWDOWN_LIQUIDATE) return { tone: "danger", label: "liquidate" };
  if (pct >= DRAWDOWN_BLOCK) return { tone: "warn", label: "block" };
  if (pct >= DRAWDOWN_WARN) return { tone: "warn", label: "warn" };
  return { tone: "success", label: "healthy" };
}

export function AccountCard() {
  const { account, error, isLoading } = useAccount();

  return (
    <Card data-testid="account-card">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Account</CardTitle>
        {account ? (
          (() => {
            const dd = Number(account.drawdown_percent);
            const { tone, label } = drawdownTone(Number.isNaN(dd) ? 0 : dd);
            return <Badge tone={tone}>drawdown {label}</Badge>;
          })()
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? (
          <div className="text-sm text-red-400">Failed to load account</div>
        ) : isLoading && !account ? (
          <div className="text-sm text-neutral-500">Loading…</div>
        ) : account ? (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-wide text-neutral-500">Balance</span>
              <span className="text-2xl font-semibold text-neutral-100">
                ${fmtNum(account.total_value, 2)}
              </span>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <dt className="text-neutral-500">Peak</dt>
              <dd className="text-right text-neutral-200">${fmtNum(account.peak, 2)}</dd>
              <dt className="text-neutral-500">Return</dt>
              <dd className="text-right text-neutral-200">
                {fmtPercent(account.return_percent, 2)}
              </dd>
              <dt className="text-neutral-500">Sharpe</dt>
              <dd className="text-right text-neutral-200">
                {account.sharpe_ratio ? fmtNum(account.sharpe_ratio, 2) : "—"}
              </dd>
              <dt className="text-neutral-500">Drawdown</dt>
              <dd className="text-right text-neutral-200">
                {fmtPercent(account.drawdown_percent, 2)}
              </dd>
              <dt className="text-neutral-500">Unrealized PnL</dt>
              <dd className="text-right text-neutral-200">
                ${fmtNum(account.unrealized_pnl, 2)}
              </dd>
              <dt className="text-neutral-500">Realized PnL</dt>
              <dd className="text-right text-neutral-200">
                ${fmtNum(account.realized_pnl, 2)}
              </dd>
            </dl>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
