"use client";

import { useAccount } from "@/hooks/useAccount";
import { fmtNum, fmtPercent } from "@/lib/utils";
import { Chip, Panel } from "./obs/Panel";

const DRAWDOWN_WARN = 5;
const DRAWDOWN_BLOCK = 10;
const DRAWDOWN_LIQUIDATE = 20;

function drawdownTone(pct: number): {
  tone: Parameters<typeof Chip>[0]["tone"];
  label: string;
} {
  if (pct >= DRAWDOWN_LIQUIDATE) return { tone: "coral", label: "liquidate" };
  if (pct >= DRAWDOWN_BLOCK) return { tone: "amber", label: "block-new" };
  if (pct >= DRAWDOWN_WARN) return { tone: "amber", label: "warn" };
  return { tone: "green", label: "healthy" };
}

export function AccountCard() {
  const { account, error, isLoading } = useAccount();

  const dd = account ? Number(account.drawdown_percent) : 0;
  const { tone, label } = drawdownTone(Number.isNaN(dd) ? 0 : dd);

  return (
    <Panel
      eyebrow="Station · Account"
      title="Vault"
      actions={account ? <Chip tone={tone}>dd {label}</Chip> : null}
      data-testid="account-card"
    >
      {error ? (
        <div className="text-sm text-obs-coral">Failed to load account</div>
      ) : isLoading && !account ? (
        <div className="text-sm text-obs-text-dim">Loading…</div>
      ) : account ? (
        <div className="space-y-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
              Balance (USDT)
            </p>
            <p className="mt-1 font-mono text-[34px] leading-none tabular-nums text-obs-text">
              <span className="text-obs-text-dim">$</span>
              {fmtNum(account.total_value, 2)}
            </p>
          </div>

          <div className="obs-hairline" />

          <dl className="grid grid-cols-2 gap-x-5 gap-y-2 font-mono text-[11px] tabular-nums">
            <div className="flex flex-col">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Peak
              </dt>
              <dd className="text-obs-text">${fmtNum(account.peak, 2)}</dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Return
              </dt>
              <dd
                className={
                  Number(account.return_percent) >= 0
                    ? "text-obs-green"
                    : "text-obs-coral"
                }
              >
                {fmtPercent(account.return_percent, 2)}
              </dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Unrealized
              </dt>
              <dd
                className={
                  Number(account.unrealized_pnl) >= 0
                    ? "text-obs-green"
                    : "text-obs-coral"
                }
              >
                ${fmtNum(account.unrealized_pnl, 2)}
              </dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Realized
              </dt>
              <dd
                className={
                  Number(account.realized_pnl) >= 0
                    ? "text-obs-green"
                    : "text-obs-coral"
                }
              >
                ${fmtNum(account.realized_pnl, 2)}
              </dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Drawdown
              </dt>
              <dd className="text-obs-text">{fmtPercent(account.drawdown_percent, 2)}</dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                Sharpe
              </dt>
              <dd className="text-obs-text">
                {account.sharpe_ratio ? fmtNum(account.sharpe_ratio, 2) : "—"}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
    </Panel>
  );
}
