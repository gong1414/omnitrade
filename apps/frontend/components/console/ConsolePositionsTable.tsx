"use client";

import { usePositions } from "@/hooks/usePositions";
import { useTranslations } from "@/lib/i18n/context";
import { fmtNum } from "@/lib/utils";
import { useTweaks } from "@/lib/console/tweaks";
import { Section } from "./Section";

function formatAge(iso: string): string {
  const opened = new Date(iso).getTime();
  if (!Number.isFinite(opened)) return "—";
  const ms = Date.now() - opened;
  if (ms < 60_000) return `${Math.max(1, Math.floor(ms / 1000))}s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`;
  return `${Math.floor(ms / 86_400_000)}d`;
}

function ClosedBar({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block w-10 h-[3px] rounded-full overflow-hidden"
        style={{ background: "var(--obs-line)" }}
      >
        <span
          className="block h-full rounded-full"
          style={{ width: `${clamped}%`, background: "var(--cd-accent)" }}
        />
      </span>
      <span className="tabular-nums" style={{ color: "var(--cd-text-mute)" }}>
        {clamped.toFixed(0)}%
      </span>
    </span>
  );
}

interface ConsolePositionsTableProps {
  maxPos?: number | null;
}

/**
 * Console-design Positions table — full-width section, 11 columns, with the
 * three-way state inline (Closed / Peak / Stop). Uses the global density
 * tweak to pick the row vertical-padding.
 */
export function ConsolePositionsTable({ maxPos }: ConsolePositionsTableProps) {
  const t = useTranslations();
  const { positions, isLoading } = usePositions();
  const { tweaks } = useTweaks();

  const rowPad = tweaks.density === "compact" ? "py-1.5" : "py-2.5";

  const subtitle = t("cd.positions.subtitle");
  const action = (
    <span
      className="text-[11px] font-mono tabular-nums"
      style={{ color: "var(--cd-text-mute)" }}
    >
      {positions.length}
      {maxPos != null ? ` / ${maxPos}` : null}
    </span>
  );

  return (
    <Section title={t("cd.positions.title")} subtitle={subtitle} action={action} flush>
      {isLoading && positions.length === 0 ? (
        <div
          className="px-5 py-6 text-[13px] font-mono"
          style={{ color: "var(--cd-text-mute)" }}
        >
          {t("common.loading")}
        </div>
      ) : positions.length === 0 ? (
        <div
          className="py-10 text-center text-[13px] font-mono"
          style={{ color: "var(--cd-text-mute)" }}
        >
          {t("cd.positions.empty")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-[12px] tabular-nums">
            <thead>
              <tr
                className="text-[10.5px] uppercase tracking-[0.14em]"
                style={{ color: "var(--cd-text-ghost)" }}
              >
                <th className="text-left pl-4 pr-3 pb-2">{t("cd.positions.symbol")}</th>
                <th className="text-left px-2 pb-2">{t("cd.positions.side")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.qty")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.entry")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.mark")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.upnl")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.lev")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.stop")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.closed_pct")}</th>
                <th className="text-right px-2 pb-2">{t("cd.positions.peak_pct")}</th>
                <th className="text-right pl-2 pr-4 pb-2">{t("cd.positions.age")}</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const pnl = Number(p.unrealized_pnl);
                const upPos = Number.isFinite(pnl) && pnl >= 0;
                const closedPct = Number(p.cumulative_close_pct) || 0;
                const peakPct = Number(p.trailing_peak_pnl_pct) || 0;
                return (
                  <tr
                    key={p.id}
                    data-testid="position-row"
                    className="border-t hover:bg-[var(--obs-panel-2)]"
                    style={{ borderColor: "var(--obs-line)" }}
                  >
                    <td className={`pl-4 pr-3 ${rowPad}`} style={{ color: "var(--obs-text)" }}>
                      {p.symbol}
                    </td>
                    <td className={`px-2 ${rowPad}`}>
                      <span
                        className="px-1.5 py-[1px] rounded text-[10px] uppercase tracking-[0.14em]"
                        style={{
                          color: p.side === "long" ? "var(--obs-green)" : "var(--obs-coral)",
                          background:
                            p.side === "long" ? "var(--cd-green-soft)" : "var(--cd-coral-soft)",
                        }}
                      >
                        {p.side === "long" ? t("cd.positions.long") : t("cd.positions.short")}
                      </span>
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--obs-text-dim)" }}>
                      {fmtNum(p.quantity, 3)}
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--obs-text-dim)" }}>
                      {fmtNum(p.entry_price, 2)}
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--obs-text)" }}>
                      {fmtNum(p.current_price, 2)}
                    </td>
                    <td
                      className={`px-2 ${rowPad} text-right`}
                      style={{ color: upPos ? "var(--obs-green)" : "var(--obs-coral)" }}
                    >
                      {upPos ? "+" : ""}
                      {fmtNum(p.unrealized_pnl, 2)}
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--cd-text-mute)" }}>
                      {p.leverage}×
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--cd-text-mute)" }}>
                      {p.stop_loss ? fmtNum(p.stop_loss, 2) : "—"}
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--cd-text-mute)" }}>
                      <ClosedBar pct={closedPct} />
                    </td>
                    <td className={`px-2 ${rowPad} text-right`} style={{ color: "var(--cd-text-mute)" }}>
                      {(peakPct * 100).toFixed(2)}%
                    </td>
                    <td className={`pl-2 pr-4 ${rowPad} text-right`} style={{ color: "var(--cd-text-mute)" }}>
                      {formatAge(p.opened_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
