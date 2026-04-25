/**
 * SSE client for the AgentOS run-events stream (Phase 5 Agno migration).
 *
 * Mirrors the public surface of `lib/ws/client.ts` so the dashboard hook
 * can drop SSE in by flag flip alone — same `ConnectionState`, same
 * `WsEnvelope` payload shape (renamed back from `EventEnvelope` for
 * cross-transport reuse).
 *
 * The default endpoint targets `/sse/stream` on the existing FastAPI host;
 * the AgentOS-side handler that re-emits trading decisions over SSE is
 * authored in Phase 4.5 alongside the AgentOS Workflow registration.
 * Until that lands the client merely connects and waits — but the wiring
 * end-to-end is already in place.
 */

import type {
  AccountUpdatePayload,
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  PositionUpdatePayload,
  WsEnvelope,
  WsEventType,
} from "../api/types";
import type { ConnectionState, WsListener, WsPayloadMap } from "../ws/client";

export type { ConnectionState, WsPayloadMap };

export interface SseClientOptions {
  url?: string;
  /** Min reconnect delay (ms). Default 1000. */
  minDelayMs?: number;
  /** Max reconnect delay (ms). Default 30000. */
  maxDelayMs?: number;
  /** Optional EventSource implementation (for tests). */
  EventSourceImpl?: typeof EventSource;
}

function resolveSseUrl(explicit?: string): string {
  if (explicit) return explicit;
  const envUrl =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_SSE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
      : undefined;
  const base = envUrl ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}/sse/stream`;
}

type AnyListener = (envelope: WsEnvelope<unknown>) => void;

export class SseClient {
  private es: EventSource | null = null;
  private url: string;
  private state: ConnectionState = "idle";
  private listeners = new Map<WsEventType, Set<AnyListener>>();
  private stateListeners = new Set<(s: ConnectionState) => void>();
  private retryAttempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private minDelay: number;
  private maxDelay: number;
  private impl: typeof EventSource;

  constructor(opts: SseClientOptions = {}) {
    this.url = resolveSseUrl(opts.url);
    this.minDelay = opts.minDelayMs ?? 1000;
    this.maxDelay = opts.maxDelayMs ?? 30000;
    this.impl = opts.EventSourceImpl ?? (typeof window !== "undefined" ? window.EventSource : (undefined as unknown as typeof EventSource));
  }

  get currentState(): ConnectionState {
    return this.state;
  }

  onState(cb: (s: ConnectionState) => void): () => void {
    this.stateListeners.add(cb);
    cb(this.state);
    return () => this.stateListeners.delete(cb);
  }

  subscribe<T extends WsEventType>(
    type: T,
    listener: WsListener<T>,
  ): () => void {
    const set = this.listeners.get(type) ?? new Set<AnyListener>();
    set.add(listener as AnyListener);
    this.listeners.set(type, set);
    return () => set.delete(listener as AnyListener);
  }

  connect(): void {
    if (!this.impl) {
      // EventSource not available (SSR or environment without DOM).
      this.setState("closed");
      return;
    }
    if (this.es && this.state === "open") return;
    this.setState(this.retryAttempt > 0 ? "reconnecting" : "connecting");
    try {
      this.es = new this.impl(this.url, { withCredentials: false });
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.es.onopen = () => {
      this.retryAttempt = 0;
      this.setState("open");
    };
    this.es.onerror = () => {
      this.es?.close();
      this.es = null;
      this.scheduleReconnect();
    };
    this.es.onmessage = (ev: MessageEvent) => this.dispatch(ev.data);
    // AgentOS may use named events per type; bind each.
    const namedTypes: WsEventType[] = [
      "account_update",
      "position_update",
      "decision_update",
      "orchestrator_error",
    ];
    for (const t of namedTypes) {
      this.es.addEventListener(t, (ev: MessageEvent) => this.dispatch(ev.data, t));
    }
  }

  disconnect(): void {
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.es?.close();
    this.es = null;
    this.setState("closed");
  }

  private dispatch(raw: unknown, fallbackType?: WsEventType): void {
    if (typeof raw !== "string" || raw.length === 0) return;
    let parsed: WsEnvelope<unknown> | null = null;
    try {
      const obj = JSON.parse(raw) as Partial<WsEnvelope<unknown>>;
      if (obj && typeof obj === "object") {
        parsed = {
          type: (obj.type as WsEventType | undefined) ?? fallbackType ?? "decision_update",
          payload: obj.payload as unknown,
          trace_id: typeof obj.trace_id === "string" ? obj.trace_id : "",
          ts: typeof obj.ts === "string" ? obj.ts : new Date().toISOString(),
        } as WsEnvelope<unknown>;
      }
    } catch {
      // Malformed event — drop silently; the WS path mirrors this behavior.
      return;
    }
    if (!parsed) return;
    const set = this.listeners.get(parsed.type);
    if (!set) return;
    for (const cb of set) cb(parsed);
  }

  private setState(next: ConnectionState): void {
    if (this.state === next) return;
    this.state = next;
    for (const cb of this.stateListeners) cb(next);
  }

  private scheduleReconnect(): void {
    this.setState("reconnecting");
    const delay = Math.min(
      this.maxDelay,
      this.minDelay * 2 ** Math.min(this.retryAttempt, 5),
    );
    const jitter = Math.random() * 250;
    this.retryAttempt += 1;
    this.retryTimer = setTimeout(() => this.connect(), delay + jitter);
  }
}

// Re-export the types so callers can `import type { ... } from "@/lib/sse/client"`
// without crossing module boundaries.
export type {
  AccountUpdatePayload,
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  PositionUpdatePayload,
  WsEnvelope,
  WsEventType,
};
