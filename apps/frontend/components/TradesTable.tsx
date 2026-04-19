"use client";

import { useTrades } from "@/hooks/useTrades";
import { cn, fmtNum } from "@/lib/utils";
import { useTranslations } from "@/lib/i18n/context";
import { Panel } from "./obs/Panel";

export function TradesTable() {
  const { trades, total, isLoading } = useTrades(50);
  const t = useTranslations("trades");

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      actions={
        <span className="font-mono text-[11px] tabular-nums text-obs-text-dim">
          {total}
        </span>
      }
      data-testid="trades-card"
      flush
    >
      {isLoading && trades.length === 0 ? (
        <div className="px-5 py-6 text-sm text-obs-text-dim">Loading…</div>
      ) : trades.length === 0 ? (
        <div className="px-5 py-6 font-mono text-[12px] text-obs-text-dim">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-x-auto font-mono text-[12px] max-h-[360px] overflow-y-auto">
          <table className="w-full">
            <thead>
              <tr className="sticky top-0 bg-obs-panel border-b border-obs-line-soft text-left uppercase tracking-[0.18em] text-[9px] text-obs-text-ghost z-[1]">
                <th className="px-5 py-2">{t("time")}</th>
                <th className="px-3 py-2">{t("symbol")}</th>
                <th className="px-3 py-2">{t("side")}</th>
                <th className="px-3 py-2">{t("type")}</th>
                <th className="px-3 py-2 text-right">{t("price")}</th>
                <th className="px-3 py-2 text-right">{t("qty")}</th>
                <th className="px-3 py-2 text-right">{t("lev")}</th>
                <th className="px-3 py-2 text-right">{t("pnl")}</th>
                <th className="px-5 py-2 text-right">{t("fee")}</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {trades.map((tr) => {
                const pnl = tr.pnl ? Number(tr.pnl) : null;
                return (
                  <tr
                    key={tr.id}
                    className="border-b border-obs-line-soft last:border-b-0 hover:bg-obs-panel-2/40"
                  >
                    <td className="px-5 py-2.5 text-obs-text-dim">
                      {new Date(tr.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </td>
                    <td className="px-3 py-2.5 text-obs-ftpink">{tr.symbol}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "px-1.5 py-[1px] text-[10px] uppercase tracking-[0.18em] border",
                          tr.side === "long"
                            ? "text-obs-green border-obs-green/40 bg-obs-green/[0.08]"
                            : "text-obs-coral border-obs-coral/40 bg-obs-coral/[0.08]",
                        )}
                      >
                        {tr.side}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "px-1.5 py-[1px] text-[10px] uppercase tracking-[0.18em] border",
                          tr.type === "open"
                            ? "text-obs-blue border-obs-blue/40 bg-obs-blue/[0.08]"
                            : "text-obs-amber border-obs-amber/40 bg-obs-amber/[0.08]",
                        )}
                      >
                        {tr.type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text">{fmtNum(tr.price, 2)}</td>
                    <td className="px-3 py-2.5 text-right text-obs-text">{fmtNum(tr.quantity, 4)}</td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">{tr.leverage}×</td>
                    <td className={cn("px-3 py-2.5 text-right", pnl !== null && (pnl >= 0 ? "text-obs-green" : "text-obs-coral"))}>
                      {pnl !== null ? fmtNum(String(pnl), 4) : "—"}
                    </td>
                    <td className="px-5 py-2.5 text-right text-obs-text-dim">
                      {tr.fee ? fmtNum(tr.fee, 4) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
