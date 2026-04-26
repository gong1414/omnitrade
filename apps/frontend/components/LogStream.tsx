"use client";

import { useState } from "react";
import { Chip, Panel, StatusDot } from "./obs/Panel";
import { useTranslations } from "@/lib/i18n/context";
import { cn, fmtTime } from "@/lib/utils";
import type { RealtimeLogEntry as WsLogEntry } from "@/hooks/useRealtime";
import type { WsEventType } from "@/lib/api/types";

const FILTERS: ("all" | WsEventType)[] = [
  "all",
  "account_update",
  "position_update",
  "decision_update",
  "orchestrator_error",
  "run_paused",
];

// Map event types to i18n filter labels.
const FILTER_KEY: Record<(typeof FILTERS)[number], string> = {
  all: "all",
  account_update: "account",
  position_update: "position",
  decision_update: "decision",
  orchestrator_error: "orchestrator",
  run_paused: "approval",
};

const toneFor: Record<WsEventType, Parameters<typeof Chip>[0]["tone"]> = {
  account_update: "green",
  position_update: "blue",
  decision_update: "violet",
  orchestrator_error: "coral",
  run_paused: "amber",
};

const dotFor: Record<WsEventType, Parameters<typeof StatusDot>[0]["tone"]> = {
  account_update: "green",
  position_update: "violet",
  decision_update: "amber",
  orchestrator_error: "coral",
  run_paused: "amber",
};

function shortPayload(payload: unknown): string {
  if (!payload) return "";
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload).slice(0, 80);
  } catch {
    return String(payload).slice(0, 80);
  }
}

export function LogStream({ log }: { log: WsLogEntry[] }) {
  const t = useTranslations("log");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const visible = filter === "all" ? log : log.filter((e) => e.type === filter);

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      data-testid="logstream-card"
      actions={
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] border transition-colors",
                filter === f
                  ? "border-obs-amber/60 bg-obs-amber/10 text-obs-amber"
                  : "border-transparent text-obs-text-ghost hover:text-obs-text",
              )}
            >
              {t(`filter.${FILTER_KEY[f]}`)}
            </button>
          ))}
        </div>
      }
      flush
    >
      {visible.length === 0 ? (
        <div className="px-5 py-6 text-sm text-obs-text-dim">{t("empty")}</div>
      ) : (
        <ul className="obs-scroll max-h-[260px] overflow-y-auto">
          {visible.map((entry) => (
            <li
              key={entry.id}
              className="px-5 py-2 border-b border-obs-line-soft last:border-b-0 font-mono text-[11px]"
              data-testid="log-row"
              data-log-type={entry.type}
            >
              <div className="flex items-center gap-2">
                <StatusDot tone={dotFor[entry.type]} />
                <Chip tone={toneFor[entry.type]}>{t(`filter.${FILTER_KEY[entry.type]}`)}</Chip>
                <span className="text-obs-text-dim tabular-nums">
                  {fmtTime(entry.ts)}
                </span>
                <span className="text-obs-text-ghost truncate ml-auto max-w-[12ch]">
                  {entry.trace_id}
                </span>
              </div>
              <p className="mt-1 pl-5 text-obs-text-dim truncate">
                {shortPayload(entry.payload)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
