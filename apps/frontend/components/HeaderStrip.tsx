"use client";

import { useEffect, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useRebate } from "@/hooks/useRebate";
import { useStats } from "@/hooks/useStats";
import { apiClient, ApiError } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import { cn, fmtNum } from "@/lib/utils";
import type { ConnectionState } from "@/lib/sse/client";
import { Chip, StatusDot } from "./obs/Panel";

export function HeaderStrip({ state }: { state: ConnectionState }) {
  const { decisions, mutate: mutateDecisions } = useDecisions({ limit: 1 });
  const { stats } = useStats();
  const { rebate } = useRebate();
  const t = useTranslations("header");
  const tc = useTranslations("common");
  const [now, setNow] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  async function onTrigger() {
    setTriggering(true);
    setTriggerMsg(null);
    try {
      const res = await apiClient.triggerCycle();
      setTriggerMsg(t("cycle.ok", { sec: res.elapsed_seconds.toFixed(1) }));
      await mutateDecisions();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setTriggerMsg(t("cycle.busy"));
      else if (e instanceof ApiError && e.status === 503) setTriggerMsg(t("cycle.disabled"));
      else setTriggerMsg(t("cycle.error"));
    } finally {
      setTriggering(false);
      setTimeout(() => setTriggerMsg(null), 4000);
    }
  }

  useEffect(() => {
    setNow(new Date().toLocaleTimeString(undefined, { hour12: false }));
    const tick = setInterval(
      () => setNow(new Date().toLocaleTimeString(undefined, { hour12: false })),
      1000,
    );
    return () => clearInterval(tick);
  }, []);

  const wsTone: Parameters<typeof StatusDot>[0]["tone"] =
    state === "open" ? "green" : state === "reconnecting" ? "amber" : "coral";
  const wsLabel = t(`ws.${state === "open" ? "open" : state === "reconnecting" ? "reconnecting" : "closed"}`);

  return (
    <header className="flex items-center justify-between gap-6 border-b border-obs-line bg-obs-ink/70 px-6 py-4">
      <div className="flex items-center gap-4 min-w-0">
        <div>
          <h1 className="font-display text-[26px] font-black leading-none text-obs-text">
            {t("brand")}
            <span className="font-mono font-normal ml-2 text-[12px] uppercase tracking-[0.28em] text-obs-text-ghost">
              {t("tagline")}
            </span>
          </h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
            {t("subtitle")}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-6 font-mono text-[11px] tabular-nums">
        {stats ? <StatsKpis stats={stats} /> : null}
        {rebate ? (
          <span
            className="flex flex-col leading-tight"
            title={t("rebate.tooltip", {
              trades: rebate.close_trades_count,
              fees: rebate.total_fees_usdt,
            })}
            data-testid="header-rebate"
          >
            <span className="text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
              {t("rebate.label")}
            </span>
            <span className="text-obs-green">
              +${fmtNum(rebate.rebate_amount_usdt, 2)}
            </span>
          </span>
        ) : null}
        <span className="flex items-center gap-2">
          <StatusDot tone={wsTone} breath={state !== "open"} />
          <span className="text-obs-text-dim uppercase tracking-[0.18em] text-[10px]">
            {wsLabel}
          </span>
        </span>
        <span className="text-obs-text">
          {t("iter", { n: decisions[0]?.iteration ?? "—" })}
        </span>
        <span className="text-obs-text-dim" suppressHydrationWarning>
          {now ?? "--:--:--"} {t("utc").toLowerCase()}
        </span>
        <button
          type="button"
          onClick={onTrigger}
          disabled={triggering}
          data-testid="cycle-trigger-btn"
          className={cn(
            "px-2 py-1 font-mono text-[10px] uppercase tracking-[0.18em] border transition-colors",
            triggering
              ? "border-obs-text-ghost/40 text-obs-text-ghost cursor-wait"
              : "border-obs-amber/60 text-obs-amber hover:bg-obs-amber/10",
          )}
          title={triggerMsg ?? t("cycle.title")}
        >
          {triggering ? tc("loading") : t("cycle.btn")}
        </button>
        {triggerMsg ? (
          <span
            className="text-[10px] text-obs-text-dim"
            data-testid="cycle-trigger-msg"
          >
            {triggerMsg}
          </span>
        ) : null}
        <Chip tone="amber">{t("testnet")}</Chip>
      </div>
    </header>
  );
}

function StatsKpis({
  stats,
}: {
  stats: NonNullable<ReturnType<typeof useStats>["stats"]>;
}) {
  const t = useTranslations("header");
  const items: Array<{ label: string; value: string; tone: "pos" | "neg" | "neutral" }> = [
    {
      label: t("kpi.return"),
      value: `${stats.total_return_percent >= 0 ? "+" : ""}${fmtNum(stats.total_return_percent, 2)}%`,
      tone: stats.total_return_percent >= 0 ? "pos" : "neg",
    },
    {
      label: t("kpi.sharpe"),
      value: Number.isFinite(stats.sharpe) ? fmtNum(stats.sharpe, 2) : "—",
      tone: "neutral",
    },
    {
      label: t("kpi.maxDd"),
      // max_drawdown is a negative fraction (e.g. -0.18 → -18%)
      value: `${fmtNum(stats.max_drawdown * 100, 2)}%`,
      tone: stats.max_drawdown < 0 ? "neg" : "neutral",
    },
    {
      label: t("kpi.winRate"),
      // win_rate is a fraction in [0, 1]
      value: `${fmtNum(stats.win_rate * 100, 1)}% · ${stats.n_trades}`,
      tone: "neutral",
    },
  ];
  return (
    <div className="flex items-center gap-4" data-testid="header-kpis">
      {items.map(({ label, value, tone }) => (
        <span key={label} className="flex flex-col leading-tight">
          <span className="text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
            {label}
          </span>
          <span
            className={cn(
              tone === "pos" ? "text-obs-green" : tone === "neg" ? "text-obs-coral" : "text-obs-text",
            )}
          >
            {value}
          </span>
        </span>
      ))}
    </div>
  );
}
