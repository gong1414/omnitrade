"use client";

import { useMemo, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useTranslations } from "@/lib/i18n/context";
import { useTweaks } from "@/lib/console/tweaks";
import { fmtNum } from "@/lib/utils";
import {
  buildStreamFromDecisions,
  type CycleMarkerEvent,
  type DecisionEvent,
  type MessageEvent,
  type StreamEvent,
  type ToolCallEvent,
  type ToolResultEvent,
} from "@/lib/stream/build";
import { Section } from "@/components/console/Section";

type Filter = "all" | "thinking" | "tools" | "decisions";

const ACTION_COLOR: Record<string, string> = {
  open: "var(--obs-green)",
  close: "var(--obs-coral)",
  partial_close: "var(--cd-accent)",
  hold: "var(--obs-violet)",
};

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return "—";
  if (ms < 60_000) return `${Math.max(1, Math.floor(ms / 1000))}s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`;
  return `${Math.floor(ms / 86_400_000)}d`;
}

interface ReasoningStreamProps {
  /** Optional override on how many decisions to fetch. */
  limit?: number;
}

/**
 * Console-design reasoning stream — the hero panel of the dashboard.
 * Renders DecisionCards inline with their structured-reasoning fields
 * (gates / invalidation / plan / confidence / justification), preserving
 * G3 acceptance: every structured field that used to live in a separate
 * panel now appears as a section within the DecisionCard, never silently
 * dropped. Legacy decisions (no structured_confidence + no justification)
 * degrade to a single paragraph note.
 */
export function ReasoningStream({ limit = 25 }: ReasoningStreamProps) {
  const t = useTranslations();
  const { tweaks } = useTweaks();
  const { decisions, count, isLoading } = useDecisions({ limit });
  const [filter, setFilter] = useState<Filter>("all");

  const events = useMemo(() => buildStreamFromDecisions(decisions), [decisions]);

  const filtered = events.filter((e) => {
    if (!tweaks.showThinking && e.kind === "message" && e.thinking) return false;
    if (!tweaks.showTools && (e.kind === "tool_call" || e.kind === "tool_result")) return false;
    if (filter === "all") return true;
    if (filter === "thinking") return e.kind === "message";
    if (filter === "tools") return e.kind === "tool_call" || e.kind === "tool_result";
    if (filter === "decisions") return e.kind === "decision";
    return true;
  });

  const action = (
    <div className="flex gap-1 font-mono text-[10.5px]">
      {(["all", "thinking", "tools", "decisions"] as Filter[]).map((f) => (
        <button
          key={f}
          onClick={() => setFilter(f)}
          className="px-2 py-1 rounded uppercase tracking-[0.14em] transition-colors"
          style={{
            color: filter === f ? "var(--cd-accent)" : "var(--cd-text-mute)",
            background: filter === f ? "var(--cd-accent-soft)" : "transparent",
          }}
        >
          {t(`cd.stream.filter.${f}`)}
        </button>
      ))}
      <span
        className="ml-2 px-2 py-1 rounded font-mono text-[10.5px] tabular-nums"
        style={{ color: "var(--cd-text-mute)" }}
      >
        {count}
      </span>
    </div>
  );

  return (
    <Section title={t("cd.stream.title")} subtitle={t("cd.stream.subtitle")} action={action}>
      <div
        className="overflow-y-auto pr-1 -mr-1"
        style={{ maxHeight: "78vh" }}
        data-testid="reasoning-feed"
      >
        {isLoading && filtered.length === 0 ? (
          <div className="px-1 py-6 text-[13px]" style={{ color: "var(--cd-text-mute)" }}>
            {t("common.loading")}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-1 py-6 text-[13px]" style={{ color: "var(--cd-text-mute)" }}>
            {t("cd.stream.empty")}
          </div>
        ) : (
          <ul className="space-y-5">
            {filtered.map((e) => (
              <li key={e.id} data-testid="reasoning-row">
                <StreamItem event={e} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

function StreamItem({ event }: { event: StreamEvent }) {
  if (event.kind === "cycle_start" || event.kind === "cycle_end") {
    return <CycleMarker event={event} />;
  }
  if (event.kind === "tool_call") return <ToolCall event={event} />;
  if (event.kind === "tool_result") return <ToolResult event={event} />;
  if (event.kind === "message") return <Message event={event} />;
  if (event.kind === "decision") return <DecisionCard event={event} />;
  return null;
}

function StreamHeader({ ts, label, accent }: { ts: string; label?: string | null; accent: string }) {
  return (
    <div
      className="flex items-center gap-2 text-[11px] font-mono px-3 pt-2"
      style={{ color: "var(--cd-text-mute)" }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: accent }} />
      {label ? <span className="uppercase tracking-[0.14em]">{label}</span> : null}
      <span className="ml-auto tabular-nums">{relTime(ts)}</span>
    </div>
  );
}

function CycleMarker({ event }: { event: CycleMarkerEvent & { kind: "cycle_start" | "cycle_end" } }) {
  const t = useTranslations();
  const isStart = event.kind === "cycle_start";
  return (
    <div className="flex items-center gap-3 py-1">
      <span
        className="font-mono text-[10.5px] uppercase tracking-[0.18em]"
        style={{ color: "var(--cd-text-ghost)" }}
      >
        {isStart ? "▸" : "▪"} {t(isStart ? "cd.stream.cycle_start" : "cd.stream.cycle_end")}
      </span>
      <span
        className="font-mono text-[10.5px] tabular-nums"
        style={{ color: "var(--cd-text-mute)" }}
      >
        #{event.iteration}
      </span>
      {event.duration_s ? (
        <span
          className="font-mono text-[10.5px] tabular-nums"
          style={{ color: "var(--cd-text-mute)" }}
        >
          {event.duration_s}s
        </span>
      ) : null}
      {event.summary ? (
        <span className="font-mono text-[10.5px]" style={{ color: "var(--obs-text-dim)" }}>
          {event.summary}
        </span>
      ) : null}
      <div className="flex-1 h-px" style={{ background: "var(--obs-line)" }} />
      <span
        className="font-mono text-[10.5px] tabular-nums"
        style={{ color: "var(--cd-text-ghost)" }}
      >
        {relTime(event.ts)}
      </span>
    </div>
  );
}

function ToolCall({ event }: { event: ToolCallEvent & { kind: "tool_call" } }) {
  const t = useTranslations();
  return (
    <div
      className="rounded-md border overflow-hidden"
      style={{ borderColor: "var(--obs-line)", background: "var(--obs-panel-2)" }}
    >
      <StreamHeader ts={event.ts} label={t("cd.stream.tool_call")} accent="var(--obs-violet)" />
      <div className="px-3 pt-2 pb-2.5">
        <div className="font-mono text-[12.5px]" style={{ color: "var(--obs-text)" }}>
          <span style={{ color: "var(--obs-violet)" }}>{event.tool}</span>
          <span style={{ color: "var(--cd-text-ghost)" }}>(</span>
          <span style={{ color: "var(--cd-text-mute)" }}>
            {Object.entries(event.args || {}).map(([k, v], i, arr) => (
              <span key={k}>
                <span>{k}=</span>
                <span style={{ color: "var(--obs-text)" }}>
                  {typeof v === "string"
                    ? `"${v}"`
                    : Array.isArray(v)
                      ? `[${(v as unknown[]).length}]`
                      : String(v)}
                </span>
                {i < arr.length - 1 ? ", " : ""}
              </span>
            ))}
          </span>
          <span style={{ color: "var(--cd-text-ghost)" }}>)</span>
        </div>
        {event.duration_ms != null ? (
          <div
            className="mt-1 font-mono text-[10.5px] tabular-nums"
            style={{ color: "var(--cd-text-ghost)" }}
          >
            {event.duration_ms} {t("cd.stream.duration_ms")}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ToolResult({ event }: { event: ToolResultEvent & { kind: "tool_result" } }) {
  const t = useTranslations();
  return (
    <div className="pl-4 border-l" style={{ borderColor: "var(--obs-line)" }}>
      <div
        className="flex items-baseline gap-2 text-[11px] font-mono"
        style={{ color: "var(--cd-text-mute)" }}
      >
        <span className="uppercase tracking-[0.14em]">↳ {t("cd.stream.tool_result")}</span>
        <span style={{ color: "var(--cd-text-ghost)" }}>{event.tool}</span>
      </div>
      <div
        className="mt-1 font-mono text-[12.5px] leading-relaxed"
        style={{ color: "var(--obs-text-dim)" }}
      >
        {event.preview}
      </div>
    </div>
  );
}

function Message({ event }: { event: MessageEvent & { kind: "message" } }) {
  const t = useTranslations();
  const isThinking = event.thinking;
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <div
          className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-semibold"
          style={{ background: "var(--cd-accent-soft)", color: "var(--cd-accent)" }}
        >
          A
        </div>
        <span
          className="text-[11px] uppercase tracking-[0.14em] font-mono"
          style={{ color: "var(--cd-text-mute)" }}
        >
          {isThinking ? t("cd.stream.thinking") : "agent"}
        </span>
        <span
          className="ml-auto text-[11px] font-mono tabular-nums"
          style={{ color: "var(--cd-text-ghost)" }}
        >
          {relTime(event.ts)}
        </span>
      </div>
      <p
        className={`text-[14.5px] leading-[1.65] ${isThinking ? "italic" : ""}`}
        style={{
          fontFamily: "var(--font-prose)",
          color: isThinking ? "var(--obs-text-dim)" : "var(--obs-text)",
        }}
      >
        {event.text}
      </p>
    </div>
  );
}

function DecisionCard({ event }: { event: DecisionEvent & { kind: "decision" } }) {
  const t = useTranslations();
  const tone = ACTION_COLOR[event.action] || "var(--obs-text)";
  const conf = event.confidence != null ? Math.round(event.confidence * 100) : null;

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: "var(--cd-line-strong)", background: "var(--obs-panel-2)" }}
    >
      <div
        className="flex items-center gap-2 px-3.5 py-2.5 border-b"
        style={{ borderColor: "var(--obs-line)" }}
      >
        <span className="w-2 h-2 rounded-full" style={{ background: tone }} />
        <span
          className="font-mono text-[11px] uppercase tracking-[0.16em] px-1.5 py-0.5 rounded"
          style={{ color: tone, background: "var(--obs-panel)" }}
        >
          {event.action}
        </span>
        {event.symbol ? (
          <span className="font-mono text-[13px]" style={{ color: "var(--obs-text)" }}>
            {event.symbol}
          </span>
        ) : null}
        {event.percentage != null ? (
          <span className="font-mono text-[11px]" style={{ color: "var(--cd-text-mute)" }}>
            {event.percentage}%
          </span>
        ) : null}
        <span
          className="ml-auto text-[11px] font-mono tabular-nums"
          style={{ color: "var(--cd-text-mute)" }}
        >
          #{event.iteration} · {relTime(event.ts)}
        </span>
      </div>

      <div className="px-3.5 py-3 space-y-3 text-[13px]">
        {event.legacy ? (
          <span
            className="inline-block text-[10px] uppercase tracking-[0.16em] font-mono"
            style={{ color: "var(--cd-text-ghost)" }}
          >
            {t("cd.stream.legacy")}
          </span>
        ) : null}

        {event.marketContext ? (
          <CardSection label={t("cd.stream.market_context")}>
            <p
              className="leading-snug"
              style={{ color: "var(--obs-text-dim)" }}
            >
              {event.marketContext}
            </p>
          </CardSection>
        ) : null}

        {event.gates && event.gates.length > 0 ? (
          <CardSection label={t("cd.stream.gates")}>
            <ul className="space-y-1">
              {event.gates.map((g, i) => (
                <li
                  key={`${event.id}-gate-${i}`}
                  className="flex gap-2 leading-snug"
                  style={{ color: "var(--obs-text-dim)" }}
                >
                  <span style={{ color: "var(--obs-green)", marginTop: 3 }}>✓</span>
                  <span>{g}</span>
                </li>
              ))}
            </ul>
          </CardSection>
        ) : null}

        {event.invalidation ? (
          <CardSection label={t("cd.stream.invalidation")}>
            <p
              className="leading-snug border-l-2 pl-2.5"
              style={{ borderColor: "var(--obs-coral)", color: "var(--obs-text-dim)" }}
            >
              {event.invalidation}
            </p>
          </CardSection>
        ) : null}

        {event.plan ? (
          <CardSection label={t("cd.stream.plan")}>
            <div className="grid grid-cols-3 gap-x-4 gap-y-1.5 font-mono text-[11.5px] tabular-nums">
              {[
                ["entry", event.plan.entry],
                ["stop", event.plan.stop_loss],
                ["tp1", event.plan.take_profit_1],
                ["tp2", event.plan.take_profit_2],
                ["risk", event.plan.risk_usd != null ? `$${fmtNum(event.plan.risk_usd, 2)}` : null],
                ["R:R", event.plan.r_multiple_target],
              ].map(([k, v]) => (
                <div
                  key={k as string}
                  className="flex items-baseline justify-between border-b border-dashed pb-1"
                  style={{ borderColor: "var(--obs-line)" }}
                >
                  <span style={{ color: "var(--cd-text-ghost)" }}>{k as string}</span>
                  <span style={{ color: "var(--obs-text)" }}>
                    {v == null ? "—" : typeof v === "number" ? fmtNum(v, 2) : (v as string)}
                  </span>
                </div>
              ))}
            </div>
          </CardSection>
        ) : null}

        {event.justification ? (
          <p
            className="italic leading-snug pt-1 border-t"
            style={{
              borderColor: "var(--obs-line)",
              color: "var(--obs-text-dim)",
              fontFamily: "var(--font-prose)",
            }}
          >
            {event.justification}
          </p>
        ) : null}

        {conf != null ? (
          <div className="flex items-center gap-3 pt-1">
            <div className="flex-1">
              <div className="flex items-baseline justify-between mb-1">
                <span
                  className="text-[10.5px] uppercase tracking-[0.16em] font-mono"
                  style={{ color: "var(--cd-text-ghost)" }}
                >
                  {t("cd.stream.confidence")}
                </span>
                <span
                  className="text-[12px] font-mono tabular-nums"
                  style={{ color: "var(--obs-text)" }}
                >
                  {conf}%
                </span>
              </div>
              <div
                className="h-1 rounded-full overflow-hidden"
                style={{ background: "var(--obs-panel)" }}
              >
                <div
                  className="h-full rounded-full"
                  style={{ width: `${conf}%`, background: tone }}
                />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CardSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="text-[10.5px] uppercase tracking-[0.16em] font-mono mb-1.5"
        style={{ color: "var(--cd-text-ghost)" }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
