"use client";

import { useEffect, useRef, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useTranslations } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import type { DecisionUpdatePayload, StageTimings, WsEnvelope } from "@/lib/api/types";
import { StatusDot } from "./obs/Panel";

type StageKey = "observe" | "news" | "think" | "decide" | "execute" | "reflect";

const STAGES: { key: StageKey; latin: string }[] = [
  { key: "observe", latin: "01" },
  { key: "news", latin: "02" },
  { key: "think", latin: "03" },
  { key: "decide", latin: "04" },
  { key: "execute", latin: "05" },
  { key: "reflect", latin: "06" },
];

const FALLBACK_STAGE_MS = 220;
const ANIMATION_SPEEDUP = 10; // replay real timings 10× so the rail animates visibly

function hasRealTimings(t?: StageTimings | null): boolean {
  if (!t) return false;
  return STAGES.some((s) => typeof t[s.key] === "number" && (t[s.key] ?? 0) >= 0);
}

export function PipelineStatus({
  lastDecisionEvent,
}: {
  lastDecisionEvent?: WsEnvelope<DecisionUpdatePayload> | null;
} = {}) {
  const { decisions } = useDecisions({ limit: 1 });
  const t = useTranslations("pipeline");
  const latestTs = decisions[0]?.timestamp ?? null;
  const latestAction = decisions[0]?.decision ?? "";
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [usingRealTimings, setUsingRealTimings] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Prefer the WS envelope timestamp so we trigger the replay at the exact
  // moment the cycle finished (not when SWR gets around to re-polling).
  const triggerTs =
    lastDecisionEvent && hasRealTimings(lastDecisionEvent.payload.stage_timings)
      ? lastDecisionEvent.ts
      : latestTs;

  useEffect(() => {
    if (!triggerTs || triggerTs === lastTs) return;
    setLastTs(triggerTs);
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const start = performance.now();

    const timings = lastDecisionEvent?.payload.stage_timings;
    const real = hasRealTimings(timings);
    setUsingRealTimings(real);

    // Build per-stage delay ladder. Real mode replays each stage's actual
    // wall-clock duration, scaled down by ANIMATION_SPEEDUP and floored at
    // 60ms so even sub-millisecond stages are visible.
    const delays: number[] = STAGES.map((s, i) => {
      if (real && timings) {
        const raw = Number(timings[s.key] ?? 0);
        return Math.max(60, raw / ANIMATION_SPEEDUP);
      }
      return i * FALLBACK_STAGE_MS;
    });

    let cumulative = 0;
    STAGES.forEach((_, i) => {
      cumulative = real ? cumulative + delays[i] : delays[i];
      const offset = cumulative;
      const tm = setTimeout(() => {
        setActiveIdx(i);
        setElapsed(Math.round(performance.now() - start));
      }, offset);
      timers.current.push(tm);
    });

    const totalMs = real
      ? cumulative
      : STAGES.length * FALLBACK_STAGE_MS;
    const reset = setTimeout(() => {
      setActiveIdx(null);
      setElapsed(null);
    }, totalMs + 1100);
    timers.current.push(reset);

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [triggerTs, lastDecisionEvent, lastTs]);

  const running = activeIdx !== null;
  const finalStageReached = activeIdx === STAGES.length - 1;
  const activeTimings = lastDecisionEvent?.payload.stage_timings;

  return (
    <div
      data-testid="pipeline-status"
      data-timings={usingRealTimings ? "real" : "fallback"}
      className="relative border border-obs-line bg-obs-panel/60 px-5 py-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
            {t("eyebrow")}
          </span>
          <span className="h-3 w-px bg-obs-line" />
          <span className="font-display text-[15px] italic text-obs-text/80">
            {running ? t("replay") : t("idle")}
          </span>
          {running && finalStageReached && latestAction ? (
            <span className="font-mono text-[11px] text-obs-green uppercase tracking-[0.18em]">
              → {latestAction}
            </span>
          ) : null}
          {!usingRealTimings ? (
            <span
              className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost"
              title={t("previewTitle")}
            >
              {t("preview")}
            </span>
          ) : null}
        </div>
        <div className="font-mono text-[11px] text-obs-text-dim tabular-nums">
          {elapsed !== null ? `${elapsed}ms` : "—"}
        </div>
      </div>

      <ol className="mt-4 grid grid-cols-6 gap-2">
        {STAGES.map((stage, i) => {
          const done = running && activeIdx !== null && i < activeIdx;
          const active = running && activeIdx === i;
          const idle = !running;
          const ms =
            usingRealTimings && activeTimings
              ? Number(activeTimings[stage.key] ?? 0)
              : null;
          return (
            <li
              key={stage.key}
              className={cn(
                "group relative flex flex-col items-start gap-1.5",
                "border-l pl-3 py-1 transition-colors duration-300",
                active ? "border-obs-green" : done ? "border-obs-violet/60" : "border-obs-line",
              )}
            >
              <div className="flex items-center gap-2">
                <StatusDot
                  tone={active ? "green" : done ? "violet" : "neutral"}
                  breath={active || (idle && i === 0)}
                />
                <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
                  {stage.latin}
                </span>
              </div>
              <span
                className={cn(
                  "font-mono text-[12px] transition-colors",
                  active ? "text-obs-green" : done ? "text-obs-text" : "text-obs-text-dim",
                )}
              >
                {t(`stage.${stage.key}`)}
              </span>
              {ms !== null ? (
                <span
                  className="font-mono text-[9px] tabular-nums text-obs-text-ghost"
                  data-testid={`pipeline-stage-${stage.key}-ms`}
                >
                  {ms < 1 ? "<1ms" : `${Math.round(ms)}ms`}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
