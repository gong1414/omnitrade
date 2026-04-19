"use client";

import { useAccount } from "@/hooks/useAccount";
import { fmtNum, fmtPercent } from "@/lib/utils";
import { useTranslations } from "@/lib/i18n/context";
import { Chip, Panel } from "./obs/Panel";

const DRAWDOWN_WARN = 5;
const DRAWDOWN_BLOCK = 10;
const DRAWDOWN_LIQUIDATE = 20;

type Tone = Parameters<typeof Chip>[0]["tone"];

function drawdownBucket(pct: number): { tone: Tone; key: "ddLiquidate" | "ddBlock" | "ddWarn" | "ddHealthy" } {
  if (pct >= DRAWDOWN_LIQUIDATE) return { tone: "coral", key: "ddLiquidate" };
  if (pct >= DRAWDOWN_BLOCK) return { tone: "amber", key: "ddBlock" };
  if (pct >= DRAWDOWN_WARN) return { tone: "amber", key: "ddWarn" };
  return { tone: "green", key: "ddHealthy" };
}

export function AccountCard() {
  const { account, error, isLoading } = useAccount();
  const t = useTranslations("account");
  const tc = useTranslations("common");

  const dd = account ? Number(account.drawdown_percent) : 0;
  const { tone, key } = drawdownBucket(Number.isNaN(dd) ? 0 : dd);

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      actions={account ? <Chip tone={tone}>{t("ddChip", { label: t(key) })}</Chip> : null}
      data-testid="account-card"
    >
      {error ? (
        <div className="text-sm text-obs-coral">{t("loadError")}</div>
      ) : isLoading && !account ? (
        <div className="text-sm text-obs-text-dim">{tc("loading")}</div>
      ) : account ? (
        <div className="space-y-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
              {t("balanceLabel")}
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
                {t("peak")}
              </dt>
              <dd className="text-obs-text">${fmtNum(account.peak, 2)}</dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                {t("return")}
              </dt>
              <dd className={Number(account.return_percent) >= 0 ? "text-obs-green" : "text-obs-coral"}>
                {fmtPercent(account.return_percent, 2)}
              </dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                {t("unrealized")}
              </dt>
              <dd className={Number(account.unrealized_pnl) >= 0 ? "text-obs-green" : "text-obs-coral"}>
                ${fmtNum(account.unrealized_pnl, 2)}
              </dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                {t("realized")}
              </dt>
              <dd className={Number(account.realized_pnl) >= 0 ? "text-obs-green" : "text-obs-coral"}>
                ${fmtNum(account.realized_pnl, 2)}
              </dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                {t("drawdown")}
              </dt>
              <dd className="text-obs-text">{fmtPercent(account.drawdown_percent, 2)}</dd>
            </div>
            <div className="flex flex-col text-right">
              <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
                {t("sharpe")}
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
