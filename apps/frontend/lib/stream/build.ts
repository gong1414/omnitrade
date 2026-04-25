/**
 * Adapter: turns the persisted `AgentDecision` rows into the Console-design
 * stream-event schema. We don't yet persist tool-call traces in the DB, so the
 * stream is decision-centric for now (one DecisionCard per row, optional
 * cycle markers grouped by iteration). When the Agno migration lands and the
 * AgentOS run trace is persisted, this adapter is the single seam to extend.
 */

import type { AgentDecision } from "@/lib/api/types";

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

/**
 * Turn a paged AgentDecision list (newest-first per backend contract) into a
 * chronological stream event list, also newest-first (so item 0 is the most
 * recent). Each decision row produces:
 *   - a `cycle_end` marker (the row's iteration boundary)
 *   - the `decision` itself (carrying all five structured fields inline)
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
