"use client";

import { useTranslations } from "@/lib/i18n/context";
import type { DecisionUpdatePayload, StageTimings, WsEnvelope } from "@/lib/api/types";
import { Section } from "./Section";

type StageKey = "observe" | "news" | "think" | "decide" | "execute" | "reflect";

const STAGES: StageKey[] = ["observe", "news", "think", "decide", "execute", "reflect"];

interface PipelineRailProps {
  lastDecisionEvent?: WsEnvelope<DecisionUpdatePayload> | null;
  iteration?: number | null;
}

/**
 * Right-column "Last cycle" pipeline rail. Shows a width-proportional bar
 * across the 6 stages and a 3-column key/value of stage durations. Falls
 * back to em-dash when no `stage_timings` have arrived yet.
 */
export function PipelineRail({ lastDecisionEvent, iteration }: PipelineRailProps) {
  const t = useTranslations();
  const timings: StageTimings = lastDecisionEvent?.payload.stage_timings ?? {};

  const segments = STAGES.map((stage) => ({
    stage,
    ms: typeof timings[stage] === "number" ? Math.max(0, timings[stage] as number) : 0,
  }));
  const total = segments.reduce((sum, s) => sum + s.ms, 0);
  const hasTimings = total > 0;
  const subtitle = iteration != null ? `cycle #${iteration}` : undefined;

  return (
    <Section title={t("cd.pipeline.title")} subtitle={subtitle}>
      <div>
        <div
          className="flex h-1.5 rounded-full overflow-hidden"
          style={{ background: "var(--obs-panel-2)" }}
        >
          {hasTimings
            ? segments.map((s, i) => (
                <div
                  key={s.stage}
                  style={{
                    width: `${(s.ms / total) * 100}%`,
                    background: i % 2 === 0 ? "var(--cd-accent)" : "var(--obs-violet)",
                    opacity: 0.85,
                  }}
                  title={`${s.stage} · ${s.ms}ms`}
                />
              ))
            : (
              <div
                className="w-full h-full"
                style={{ background: "var(--obs-line)", opacity: 0.6 }}
              />
            )}
        </div>
        <div
          className="mt-3 grid grid-cols-3 gap-x-3 gap-y-1.5 font-mono text-[11px]"
          data-testid="pipeline-status"
        >
          {STAGES.map((stage) => {
            const ms = timings[stage];
            return (
              <div
                key={stage}
                className="flex justify-between border-b border-dashed pb-1"
                style={{ borderColor: "var(--obs-line)" }}
                data-testid={`pipeline-stage-${stage}-ms`}
              >
                <span style={{ color: "var(--cd-text-ghost)" }}>
                  {t(`cd.pipeline.${stage}`)}
                </span>
                <span className="tabular-nums" style={{ color: "var(--obs-text-dim)" }}>
                  {typeof ms === "number" ? `${(ms / 1000).toFixed(2)}s` : "—"}
                </span>
              </div>
            );
          })}
        </div>
        <div
          className="mt-2 text-right font-mono text-[10.5px] tabular-nums"
          style={{ color: "var(--cd-text-ghost)" }}
        >
          Σ {hasTimings ? `${(total / 1000).toFixed(2)}s` : "—"}
        </div>
      </div>
    </Section>
  );
}
