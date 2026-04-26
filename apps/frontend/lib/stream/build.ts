/**
 * Adapter: turns the persisted `AgentDecision` rows into the Console-design
 * stream-event schema. Each decision can carry an optional `trace` array
 * (returned by the backend when the request includes ``?include=trace``)
 * that's flattened from the matching Agno run's messages — assistant
 * `reasoning_content` becomes `thinking` events, `tool_calls` become
 * `tool_call` events, and tool-role messages become `tool_result` events.
 * Decisions older than the active Agno session window or rows imported
 * from the legacy LangGraph era come through with `trace: []` and
 * degrade gracefully to the decision-centric stream.
 */

import type { AgentDecision, AgentDecisionTraceEvent } from "@/lib/api/types";

export type StreamEvent =
  | (CycleMarkerEvent & { kind: "cycle_start" | "cycle_end" })
  | (DecisionEvent & { kind: "decision" })
  | (MessageEvent & { kind: "message" })
  | (ToolCallEvent & { kind: "tool_call" })
  | (ToolResultEvent & { kind: "tool_result" });

interface BaseEvent {
  id: string;
  ts: string;
}

export interface CycleMarkerEvent extends BaseEvent {
  iteration: number;
  duration_s?: number;
  summary?: string;
  label?: string;
}

export interface DecisionEvent extends BaseEvent {
  decisionId: number;
  iteration: number;
  action: string;
  symbol: string | null;
  side: string | null;
  percentage: number | null;
  confidence: number | null;
  gates: string[];
  invalidation: string | null;
  marketContext: string | null;
  plan: AgentDecision["plan"] | null;
  justification: string | null;
  outputLanguage: string | null;
  legacy: boolean;
}

export interface MessageEvent extends BaseEvent {
  role: "assistant" | "user" | "system";
  thinking?: boolean;
  text: string;
}

export interface ToolCallEvent extends BaseEvent {
  tool: string;
  args: Record<string, unknown>;
  duration_ms?: number;
}

export interface ToolResultEvent extends BaseEvent {
  tool: string;
  preview: string;
}

interface ActionStep {
  tool?: string;
  symbol?: string;
  side?: string;
  percentage?: number;
  size?: number | string;
  leverage?: number;
  reason?: string;
  reasoning?: string;
}

function safeParseArray<T>(raw: string | undefined | null): T[] {
  if (!raw) return [];
  try {
    const out = JSON.parse(raw);
    return Array.isArray(out) ? (out as T[]) : [];
  } catch {
    return [];
  }
}

function epochToIso(seconds: number | null | undefined, fallback: string): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return fallback;
  return new Date(seconds * 1000).toISOString();
}

function previewArgs(args: unknown): Record<string, unknown> {
  if (args && typeof args === "object" && !Array.isArray(args)) {
    return args as Record<string, unknown>;
  }
  if (typeof args === "string") return { _raw: args };
  return {};
}

/**
 * Project a single decision's `trace` array into the dashboard's stream
 * event types, preserving the Agno run order (oldest → newest).
 */
function traceToEvents(
  trace: AgentDecisionTraceEvent[] | null | undefined,
  decisionId: number,
  fallbackTs: string,
): StreamEvent[] {
  if (!Array.isArray(trace) || trace.length === 0) return [];
  const out: StreamEvent[] = [];
  trace.forEach((ev, idx) => {
    const ts = epochToIso(ev.created_at, fallbackTs);
    if (ev.kind === "thinking") {
      out.push({
        kind: "message",
        id: `decision-${decisionId}-thinking-${idx}`,
        ts,
        role: "assistant",
        thinking: true,
        text: ev.content ?? "",
      });
    } else if (ev.kind === "tool_call") {
      out.push({
        kind: "tool_call",
        id: `decision-${decisionId}-tool-call-${ev.id ?? idx}`,
        ts,
        tool: ev.tool ?? "tool",
        args: previewArgs(ev.args),
      });
    } else if (ev.kind === "tool_result") {
      const preview =
        typeof ev.preview === "string"
          ? ev.preview
          : JSON.stringify(ev.preview ?? null).slice(0, 1024);
      out.push({
        kind: "tool_result",
        id: `decision-${decisionId}-tool-result-${ev.id ?? idx}`,
        ts,
        tool: ev.tool ?? "tool",
        preview,
      });
    }
  });
  return out;
}

/**
 * Turn a paged AgentDecision list (newest-first per backend contract) into a
 * chronological stream event list, also newest-first (so item 0 is the most
 * recent). Each decision row produces:
 *   - a `cycle_end` marker (the row's iteration boundary)
 *   - the `decision` itself (carrying all five structured fields inline)
 *   - a flattened trace if `?include=trace` was requested (assistant
 *     thinking + tool_call + tool_result events the LLM emitted that cycle).
 *
 * Within a cycle, events are ordered: `decision` first (so the card shows
 * up top), then trace events oldest → newest (inner monologue), then the
 * `cycle_end` marker. Across cycles the array stays newest-cycle-first.
 */
export function buildStreamFromDecisions(decisions: AgentDecision[]): StreamEvent[] {
  const events: StreamEvent[] = [];
  for (const d of decisions) {
    const actions = safeParseArray<ActionStep>(d.actions_taken);
    const primary = actions[0] ?? null;
    const action = (primary?.tool ?? d.decision ?? "hold").toString();
    const legacy = d.structured_confidence == null && !d.justification;
    const justification =
      d.justification ?? primary?.reason ?? primary?.reasoning ?? d.decision ?? null;

    events.push({
      kind: "decision",
      id: `decision-${d.id}`,
      ts: d.timestamp,
      decisionId: d.id,
      iteration: d.iteration,
      action,
      symbol: primary?.symbol ?? null,
      side: primary?.side ?? null,
      percentage: typeof primary?.percentage === "number" ? primary.percentage : null,
      confidence: d.structured_confidence ?? null,
      gates: d.gates_passed ?? [],
      invalidation: d.invalidation_condition ?? null,
      marketContext: d.market_context ?? null,
      plan: d.plan ?? null,
      justification,
      outputLanguage: d.output_language ?? null,
      legacy,
    });

    events.push(...traceToEvents(d.trace, d.id, d.timestamp));

    events.push({
      kind: "cycle_end",
      id: `cycle-end-${d.id}`,
      ts: d.timestamp,
      iteration: d.iteration,
      summary: action,
    });
  }
  return events;
}
