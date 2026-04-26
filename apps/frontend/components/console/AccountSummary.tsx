"use client";

import useSWR from "swr";
import { useAccount } from "@/hooks/useAccount";
import { apiClient } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import type { HistoryResponse } from "@/lib/api/types";
import { fmtNum } from "@/lib/utils";
import { Section, Sparkline } from "./Section";

const HISTORY_KEY = "/api/history?window=24h";

/**
 * Right-column Account summary card. Big tabular balance, equity sparkline
 * (24h history), then a 2-column key/value of available / realised.
 */
export function AccountSummary() {
  const t = useTranslations();
  const { account, isLoading } = useAccount();
  const { data: history } = useSWR<HistoryResponse>(
    HISTORY_KEY,
    () => apiClient.fetchHistory("24h"),
    // SSE `account_update` triggers a global mutate of every
    // `/api/history*` key, so the periodic poll would only ever return
    // the same row that the recorder just emitted.
    { revalidateOnFocus: false },
  );

  const points = history
    ? history.timestamps.map((ts, i) => ({ t: ts, v: history.total_value[i] ?? 0 }))
    : [];

  const peakSub = account ? `peak $${fmtNum(account.peak, 0)}` : undefined;

  return (
    <Section title={t("cd.account.title")} subtitle={peakSub}>
      <div className="space-y-3">
        <div>
          <div
            className="text-[11px] uppercase tracking-[0.14em] font-mono mb-1"
            style={{ color: "var(--cd-text-ghost)" }}
          >
            {t("cd.account.balance")}
          </div>
          <div className="text-[28px] font-medium tabular-nums leading-none">
            {account ? `$${fmtNum(account.total_value, 2)}` : isLoading ? "—" : "—"}
          </div>
        </div>
        <Sparkline points={points} height={48} />
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11.5px] pt-1">
          <Row k={t("cd.account.available")} v={account ? `$${fmtNum(account.available_cash, 2)}` : "—"} />
          <Row k={t("cd.account.realized")} v={account ? `$${fmtNum(account.realized_pnl, 2)}` : "—"} />
        </div>
      </div>
    </Section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <span style={{ color: "var(--cd-text-ghost)" }}>{k}</span>
      <span className="tabular-nums" style={{ color: "var(--obs-text-dim)" }}>{v}</span>
    </div>
  );
}
