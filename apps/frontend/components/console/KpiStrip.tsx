"use client";

import { useAccount } from "@/hooks/useAccount";
import { useRebate } from "@/hooks/useRebate";
import { useStats } from "@/hooks/useStats";
import { useTranslations } from "@/lib/i18n/context";
import { fmtNum } from "@/lib/utils";

interface KpiCellProps {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}

function KpiCell({ label, value, sub, tone }: KpiCellProps) {
  return (
    <div
      className="flex flex-col gap-1 px-4 py-3 border-r last:border-r-0 min-w-0"
      style={{ borderColor: "var(--obs-line)" }}
    >
      <div
        className="text-[10.5px] uppercase tracking-[0.16em] font-mono"
        style={{ color: "var(--cd-text-ghost)" }}
      >
        {label}
      </div>
      <div
        className="text-[18px] font-medium tabular-nums truncate"
        style={{ color: tone || "var(--obs-text)" }}
      >
        {value}
      </div>
      {sub ? (
        <div
          className="text-[11px] font-mono tabular-nums"
          style={{ color: "var(--cd-text-mute)" }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 6-cell KPI strip across the top of the dashboard.
 * Equity / Return / Unrealized / Sharpe / Drawdown / Rebate (24h).
 *
 * Reads `useAccount` (per-row precision values), `useStats` (Sharpe / DD),
 * `useRebate` (24h rolling). All cells gracefully render `—` when sources
 * haven't hydrated yet.
 */
export function KpiStrip({ initialBalance }: { initialBalance: number | null }) {
  const t = useTranslations();
  const { account } = useAccount();
  const { stats } = useStats();
  const { rebate } = useRebate();

  const equity = account ? Number(account.total_value) : null;
  const peak = account ? Number(account.peak) : null;
  const ret = account
    ? Number(account.return_percent)
    : stats?.total_return_percent ?? null;
  const unrealized = account ? Number(account.unrealized_pnl) : null;
  const realized = account ? Number(account.realized_pnl) : null;
  const sharpe = account?.sharpe_ratio
    ? Number(account.sharpe_ratio)
    : stats?.sharpe ?? null;
  const dd = account ? Number(account.drawdown_percent) : null;
  const ddPct = stats?.max_drawdown != null ? stats.max_drawdown * 100 : null;

  const retTone =
    ret == null ? "var(--obs-text)" : ret >= 0 ? "var(--obs-green)" : "var(--obs-coral)";
  const unrealizedTone =
    unrealized == null
      ? "var(--obs-text)"
      : unrealized >= 0
        ? "var(--obs-green)"
        : "var(--obs-coral)";
  const ddSource = dd ?? ddPct;
  const ddTone =
    ddSource == null
      ? "var(--obs-text)"
      : ddSource <= -10
        ? "var(--obs-coral)"
        : ddSource <= -5
          ? "var(--cd-accent)"
          : "var(--obs-text)";

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 rounded-lg border overflow-hidden"
      style={{ borderColor: "var(--obs-line)", background: "var(--obs-panel)" }}
    >
      <KpiCell
        label={t("cd.kpi.equity")}
        value={equity != null ? `$${fmtNum(equity, 2)}` : "—"}
        sub={peak != null ? `peak $${fmtNum(peak, 0)}` : undefined}
      />
      <KpiCell
        label={t("cd.kpi.return")}
        value={ret != null ? `${ret >= 0 ? "+" : ""}${fmtNum(ret, 2)}%` : "—"}
        sub={initialBalance != null ? `init $${fmtNum(initialBalance, 0)}` : undefined}
        tone={retTone}
      />
      <KpiCell
        label={t("cd.kpi.unrealized")}
        value={
          unrealized != null
            ? `${unrealized >= 0 ? "+" : ""}$${fmtNum(unrealized, 2)}`
            : "—"
        }
        sub={realized != null ? `realised $${fmtNum(realized, 0)}` : undefined}
        tone={unrealizedTone}
      />
      <KpiCell
        label={t("cd.kpi.sharpe")}
        value={sharpe != null && Number.isFinite(sharpe) ? fmtNum(sharpe, 2) : "—"}
        sub="rolling 30d"
      />
      <KpiCell
        label={t("cd.kpi.drawdown")}
        value={ddSource != null ? `${fmtNum(ddSource, 2)}%` : "—"}
        sub="from peak"
        tone={ddTone}
      />
      <KpiCell
        label={t("cd.kpi.rebate")}
        value={rebate ? `$${fmtNum(rebate.rebate_amount_usdt, 2)}` : "—"}
        sub="24h cumulative"
      />
    </div>
  );
}
