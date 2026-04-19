"use client";

import { useState } from "react";
import { usePositions } from "@/hooks/usePositions";
import { apiClient } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import { cn, fmtNum, fmtPercent } from "@/lib/utils";
import { Panel } from "./obs/Panel";
import { Button } from "./ui/button";
import { Dialog, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import type { Position } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";

function formatAge(iso: string): string {
  const opened = new Date(iso).getTime();
  if (!Number.isFinite(opened)) return "—";
  const mins = Math.max(0, Math.floor((Date.now() - opened) / 60_000));
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m`;
  const days = Math.floor(hrs / 24);
  return `${days}d ${hrs % 24}h`;
}

export function PositionsTable() {
  const { positions, isLoading, mutate } = usePositions();
  const t = useTranslations("positions");
  const tc = useTranslations("common");
  const [target, setTarget] = useState<Position | null>(null);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClose() {
    if (!target) return;
    setSubmitting(true);
    setErr(null);
    try {
      await apiClient.closePosition({ symbol: target.symbol, password });
      await mutate();
      setTarget(null);
      setPassword("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to close position";
      setErr(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      actions={
        <span className="font-mono text-[11px] tabular-nums text-obs-text-dim">
          {positions.length}
        </span>
      }
      data-testid="positions-card"
      flush
    >
      {isLoading && positions.length === 0 ? (
        <div className="px-5 py-6 text-sm text-obs-text-dim">{tc("loading")}</div>
      ) : positions.length === 0 ? (
        <div className="px-5 py-6 font-mono text-[12px] text-obs-text-dim">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-x-auto font-mono text-[12px]">
          <table className="w-full">
            <thead>
              <tr className="border-b border-obs-line-soft text-left uppercase tracking-[0.18em] text-[9px] text-obs-text-ghost">
                <th className="px-5 py-2">{t("symbol")}</th>
                <th className="px-3 py-2">{t("side")}</th>
                <th className="px-3 py-2 text-right">{t("qty")}</th>
                <th className="px-3 py-2 text-right">{t("entry")}</th>
                <th className="px-3 py-2 text-right">{t("mark")}</th>
                <th className="px-3 py-2 text-right">{t("pnl")}</th>
                <th className="px-3 py-2 text-right">{t("lev")}</th>
                <th className="px-3 py-2 text-right">{t("stopLoss")}</th>
                <th className="px-3 py-2 text-right">{t("closed")}</th>
                <th className="px-3 py-2 text-right">{t("peak")}</th>
                <th className="px-3 py-2 text-right">{t("age")}</th>
                <th className="px-5 py-2 text-right" />
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {positions.map((p) => {
                const pnl = Number(p.unrealized_pnl);
                return (
                  <tr
                    key={p.id}
                    data-testid="position-row"
                    className="border-b border-obs-line-soft last:border-b-0 hover:bg-obs-panel-2/40"
                  >
                    <td className="px-5 py-2.5 text-obs-ftpink">{p.symbol}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={cn(
                          "px-1.5 py-[1px] text-[10px] uppercase tracking-[0.18em] border",
                          p.side === "long"
                            ? "text-obs-green border-obs-green/40 bg-obs-green/[0.08]"
                            : "text-obs-coral border-obs-coral/40 bg-obs-coral/[0.08]",
                        )}
                      >
                        {p.side}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text">{fmtNum(p.quantity, 4)}</td>
                    <td className="px-3 py-2.5 text-right text-obs-text">{fmtNum(p.entry_price, 4)}</td>
                    <td className="px-3 py-2.5 text-right text-obs-text">{fmtNum(p.current_price, 4)}</td>
                    <td className={cn("px-3 py-2.5 text-right", pnl >= 0 ? "text-obs-green" : "text-obs-coral")}>
                      {fmtNum(p.unrealized_pnl, 2)}
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">{p.leverage}×</td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">
                      {p.stop_loss ? fmtNum(p.stop_loss, 2) : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">
                      {fmtNum(p.cumulative_close_pct, 0)}%
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">
                      {fmtPercent(p.trailing_peak_pnl_pct, 2)}
                    </td>
                    <td className="px-3 py-2.5 text-right text-obs-text-dim">
                      {formatAge(p.opened_at)}
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => setTarget(p)}
                        data-testid="close-button"
                        className="font-mono text-[10px] uppercase tracking-[0.18em]"
                      >
                        {tc("close")}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        open={target !== null}
        onOpenChange={(o) => {
          if (!o) {
            setTarget(null);
            setPassword("");
            setErr(null);
          }
        }}
        title={target ? t("confirmTitle", { symbol: target.symbol }) : undefined}
      >
        <p className="text-sm text-obs-text-dim">{t("confirmBody")}</p>
        <div className="mt-4 space-y-2">
          <Input
            type="password"
            placeholder={t("passwordPlaceholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            data-testid="close-password"
          />
          {err ? <p className="text-xs text-obs-coral">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setTarget(null)} disabled={submitting}>
            {tc("cancel")}
          </Button>
          <Button
            variant="destructive"
            onClick={onClose}
            disabled={submitting || password.length === 0}
            data-testid="close-submit"
          >
            {submitting ? tc("closing") : t("confirmSubmit")}
          </Button>
        </DialogFooter>
      </Dialog>
    </Panel>
  );
}
