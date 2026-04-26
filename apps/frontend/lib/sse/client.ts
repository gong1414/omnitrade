/**
 * SSE client for the FastAPI `/sse/stream` route — the dashboard's only
 * realtime transport after Stage C of the Agno cutover. Replaces the
 * legacy `lib/ws/client.ts` while preserving the same `WsEnvelope`
 * payload shape so consumers don't have to rewrite their type imports.
 */

import type {
  AccountUpdatePayload,
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  PositionUpdatePayload,
  RunPausedPayload,
  WsEnvelope,
  WsEventType,
} from "../api/types";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "reconnecting";

export type WsPayloadMap = {
  account_update: AccountUpdatePayload;
  position_update: PositionUpdatePayload;
  decision_update: DecisionUpdatePayload;
  orchestrator_error: OrchestratorErrorPayload;
  run_paused: RunPausedPayload;
};

export type WsListener<T extends WsEventType> = (
  envelope: WsEnvelope<WsPayloadMap[T]>,
) => void;

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
  // Default to a relative URL so EventSource hits the Next same-origin
  // proxy at `/sse/stream` (declared in `next.config.mjs`). The proxy
  // forwards into the Docker network where the backend lives — opaque
  // to whichever IP the browser is on.
  const base = envUrl ?? "";
  return `${base.replace(/\/$/, "")}/sse/stream`;
}

type AnyListener = (envelope: WsEnvelope<unknown>) => void;

export class SseClient {
  private es: EventSource | null = null;
  private url: string;
  private _state: ConnectionState = "idle";
  private _lastDisconnectAt: number | null = null;
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

  // Surface the same shape the dashboard hook expected from `WsClient`
  // (`state`, `onStateChange`, `lastDisconnectAt`) so the realtime
  // singleton can swap one for the other without changing call sites.
  get state(): ConnectionState {
    return this._state;
  }

  /** @deprecated Kept for callers that still read `currentState`. */
  get currentState(): ConnectionState {
    return this._state;
  }

  get lastDisconnectAt(): number | null {
    return this._lastDisconnectAt;
  }

  onStateChange(cb: (s: ConnectionState) => void): () => void {
    return this.onState(cb);
  }

  onState(cb: (s: ConnectionState) => void): () => void {
    this.stateListeners.add(cb);
    cb(this._state);
    return () => {
      this.stateListeners.delete(cb);
    };
  }

  subscribe<T extends WsEventType>(
    type: T,
    listener: WsListener<T>,
  ): () => void {
    const set = this.listeners.get(type) ?? new Set<AnyListener>();
    set.add(listener as AnyListener);
    this.listeners.set(type, set);
    return () => {
      set.delete(listener as AnyListener);
    };
  }

  connect(): void {
    if (!this.impl) {
      // EventSource not available (SSR or environment without DOM).
      this.setState("closed");
      return;
    }
    if (this.es && this._state === "open") return;
    this.setState(this.retryAttempt > 0 ? "reconnecting" : "connecting");
    try {
      this.es = new this.impl(this.url, { withCredentials: false });
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.es.onopen = () => {
      this.retryAttempt = 0;
      this._lastDisconnectAt = null;
      this.setState("open");
    };
    this.es.onerror = () => {
      this.es?.close();
      this.es = null;
      this._lastDisconnectAt = Date.now();
      this.scheduleReconnect();
    };
    this.es.onmessage = (ev: MessageEvent) => this.dispatch(ev.data);
    // AgentOS may use named events per type; bind each.
    const namedTypes: WsEventType[] = [
      "account_update",
      "position_update",
      "decision_update",
      "orchestrator_error",
      "run_paused",
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
    if (this.es) {
      this.es.close();
      this.es = null;
      this._lastDisconnectAt = Date.now();
    }
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
    if (this._state === next) return;
    this._state = next;
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
  RunPausedPayload,
  WsEnvelope,
  WsEventType,
};
