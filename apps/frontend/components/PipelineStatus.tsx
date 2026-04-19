"use client";

import { useEffect, useRef, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useTranslations } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
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

const STAGE_MS = 220;

export function PipelineStatus() {
  const { decisions } = useDecisions({ limit: 1 });
  const t = useTranslations("pipeline");
  const latestTs = decisions[0]?.timestamp ?? null;
  const latestAction = decisions[0]?.decision ?? "";
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [lastTs, setLastTs] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (!latestTs || latestTs === lastTs) return;
    setLastTs(latestTs);
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const start = performance.now();
    STAGES.forEach((_, i) => {
      const tm = setTimeout(() => {
        setActiveIdx(i);
        setElapsed(Math.round(performance.now() - start));
      }, i * STAGE_MS);
      timers.current.push(tm);
    });
    const reset = setTimeout(
      () => {
        setActiveIdx(null);
        setElapsed(null);
      },
      STAGES.length * STAGE_MS + 1100,
    );
    timers.current.push(reset);
    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [latestTs, lastTs]);

  const running = activeIdx !== null;
  const finalStageReached = activeIdx === STAGES.length - 1;

  return (
    <div
      data-testid="pipeline-status"
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
            </li>
          );
        })}
      </ol>
    </div>
  );
}
