"use client";

import { useMemo, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useTranslations } from "@/lib/i18n/context";
import { cn, fmtNum, fmtTime } from "@/lib/utils";
import { Chip, Panel, StatusDot } from "./obs/Panel";
import { MarketContextPanel } from "./reasoning/MarketContextPanel";
import { GatesPanel } from "./reasoning/GatesPanel";
import { InvalidationCard } from "./reasoning/InvalidationCard";
import { PlanCard } from "./reasoning/PlanCard";
import { ConfidenceGauge } from "./reasoning/ConfidenceGauge";
import { JustificationPanel } from "./reasoning/JustificationPanel";
import type { AgentDecision } from "@/lib/api/types";

interface ActionStep {
  tool?: string;
  reason?: string;
  reasoning?: string;
  symbol?: string;
  side?: string;
  percentage?: number;
  size?: number | string;
  leverage?: number;
  [k: string]: unknown;
}

function pickReason(step: ActionStep | null, fallback: string | undefined): string {
  const raw = step?.reason ?? step?.reasoning ?? fallback ?? "";
  return typeof raw === "string" ? raw : String(raw);
}

function parseActions(raw: string | undefined): ActionStep[] {
  if (!raw) return [];
  try {
    const data = JSON.parse(raw);
    return Array.isArray(data) ? (data as ActionStep[]) : [];
  } catch {
    return [];
  }
}

function parseMarket(raw: string | undefined): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch {
    return null;
  }
}

function hasStructured(d: AgentDecision): boolean {
  return d.structured_confidence != null;
}

function toneForAction(action: string): Parameters<typeof Chip>[0]["tone"] {
  const a = action.toLowerCase();
  if (a === "open") return "green";
  if (a === "close") return "coral";
  if (a === "partial_close") return "amber";
  if (a === "hold") return "violet";
  return "neutral";
}

function marketSummary(m: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  for (const [sym, data] of Object.entries(m).slice(0, 4)) {
    if (!data || typeof data !== "object") continue;
    const obj = data as Record<string, unknown>;
    const price =
      typeof obj.price === "number" || typeof obj.price === "string"
        ? obj.price
        : obj.last ?? null;
    const fr =
      typeof obj.fundingRate === "number" || typeof obj.fundingRate === "string"
        ? obj.fundingRate
        : null;
    const parts: string[] = [];
    if (price !== null && price !== undefined) parts.push(`px ${fmtNum(price as string | number, 2)}`);
    if (fr !== null && fr !== undefined) parts.push(`fr ${Number(fr).toExponential(2)}`);
    rows.push([sym, parts.join("  ·  ")]);
  }
  return rows;
}

export function AgentReasoningFeed() {
  const { decisions, isLoading, count } = useDecisions({ limit: 25 });
  const t = useTranslations("reasoning");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const rows = useMemo(
    () =>
      decisions.map((d) => {
        const actions = parseActions(d.actions_taken);
        const market = parseMarket(d.market_analysis);
        return { raw: d, actions, market, primary: actions[0] ?? null };
      }),
    [decisions],
  );

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      data-testid="reasoning-feed"
      actions={
        <span className="font-mono text-[11px] text-obs-text-dim tabular-nums">
          {count}
        </span>
      }
      flush
    >
      {isLoading && rows.length === 0 ? (
        <div className="px-5 py-6 text-sm text-obs-text-dim">{t("awaiting")}</div>
      ) : rows.length === 0 ? (
        <div className="px-5 py-6 text-sm text-obs-text-dim">{t("quiet")}</div>
      ) : (
        <ul className="obs-scroll max-h-[720px] overflow-y-auto">
          {rows.map(({ raw, actions, market, primary }, idx) => {
            const reason = pickReason(primary, raw.decision);
            const action = (primary?.tool ?? raw.decision ?? "—") as string;
            const summary = market ? marketSummary(market) : [];
            const isExpanded = expandedId === raw.id;
            const hasLongReason = reason.length > 260;
            const extra = actions.length - 1;

            return (
              <li
                key={raw.id}
                data-testid="reasoning-row"
                className={cn(
                  "px-5 py-4 border-b border-obs-line-soft last:border-b-0",
                  idx === 0 ? "obs-slide-in" : "",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot
                      tone={
                        action === "hold"
                          ? "violet"
                          : action === "open"
                            ? "green"
                            : action === "close" || action === "partial_close"
                              ? "coral"
                              : "neutral"
                      }
                    />
                    <Chip tone={toneForAction(action)}>{action}</Chip>
                    <span className="font-mono text-[10px] text-obs-text-ghost uppercase tracking-[0.18em]">
                      #{raw.iteration}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-obs-text-dim tabular-nums">
                    {fmtTime(raw.timestamp)}
                  </span>
                </div>

                {primary && (primary.symbol || primary.side) ? (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
                    <span className="text-obs-text-dim">{t("call")}</span>
                    <span className="text-obs-violet">{primary.tool}</span>
                    <span className="text-obs-text-ghost">(</span>
                    {primary.symbol ? (
                      <span className="text-obs-text">
                        symbol=<span className="text-obs-ftpink">{primary.symbol}</span>
                      </span>
                    ) : null}
                    {primary.side ? (
                      <span className="text-obs-text">
                        side=<span className="text-obs-ftpink">{primary.side}</span>
                      </span>
                    ) : null}
                    {primary.leverage !== undefined ? (
                      <span className="text-obs-text">
                        lev=<span className="text-obs-ftpink">{primary.leverage}×</span>
                      </span>
                    ) : null}
                    {primary.size !== undefined ? (
                      <span className="text-obs-text">
                        size=<span className="text-obs-ftpink">{String(primary.size)}</span>
                      </span>
                    ) : null}
                    {primary.percentage !== undefined ? (
                      <span className="text-obs-text">
                        pct=<span className="text-obs-ftpink">{primary.percentage}</span>
                      </span>
                    ) : null}
                    <span className="text-obs-text-ghost">)</span>
                  </div>
                ) : null}

                {hasStructured(raw) ? (
                  <>
                    <MarketContextPanel decision={raw} />
                    <GatesPanel decision={raw} />
                    <InvalidationCard decision={raw} />
                    {raw.plan && <PlanCard plan={raw.plan} />}
                    <ConfidenceGauge value={raw.structured_confidence} />
                    <JustificationPanel text={raw.justification ?? reason} />
                  </>
                ) : reason ? (
                  <blockquote
                    data-testid="reasoning-text"
                    className={cn(
                      "mt-3 border-l-2 border-obs-amber/50 pl-4",
                      "font-sans text-[15px] leading-[1.55] italic text-obs-text/90",
                    )}
                  >
                    {hasLongReason && !isExpanded
                      ? `${reason.slice(0, 260).trim()}…`
                      : reason}
                    {hasLongReason ? (
                      <button
                        type="button"
                        onClick={() => setExpandedId(isExpanded ? null : raw.id)}
                        className="mt-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-obs-amber hover:text-obs-text"
                      >
                        {isExpanded ? t("collapse") : t("expand")}
                      </button>
                    ) : null}
                  </blockquote>
                ) : null}

                {summary.length ? (
                  <div className="mt-3 border border-dashed border-obs-line px-3 py-2">
                    <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost mb-1">
                      {t("snapshot")}
                    </p>
                    <ul className="font-mono text-[11px] space-y-0.5">
                      {summary.map(([sym, desc]) => (
                        <li key={sym} className="flex gap-3">
                          <span className="text-obs-ftpink w-20 shrink-0">{sym}</span>
                          <span className="text-obs-text-dim">{desc || "—"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="mt-3 flex items-center justify-between font-mono text-[10px] text-obs-text-ghost">
                  <span>
                    {extra > 0
                      ? extra === 1
                        ? t("moreSteps", { n: extra })
                        : t("moreStepsPlural", { n: extra })
                      : ""}
                  </span>
                  {raw.run_id ? (
                    <span className="truncate max-w-[16ch]" title={raw.run_id}>
                      {raw.run_id}
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
