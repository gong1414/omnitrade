/**
 * WebSocket client for `/ws/stream` with exponential backoff (1/2/4/8/16, max 30s).
 *
 * Features:
 *   - EventTarget-free typed subscribe API (keeps the wrapper SSR-safe).
 *   - Exponential reconnect with jitter.
 *   - Ping/pong keepalive (text "ping" → "pong" per Phase 5 contract).
 *   - Connection state callbacks ("connected" | "disconnected").
 */

import type {
  AccountUpdatePayload,
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  PositionUpdatePayload,
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
};

export type WsListener<T extends WsEventType> = (
  envelope: WsEnvelope<WsPayloadMap[T]>,
) => void;

type AnyListener = (envelope: WsEnvelope<unknown>) => void;

export interface WsClientOptions {
  url?: string;
  /** Min reconnect delay (ms). Default 1000. */
  minDelayMs?: number;
  /** Max reconnect delay (ms). Default 30000. */
  maxDelayMs?: number;
  /** Ping every N ms. Default 15000. 0 disables. */
  pingIntervalMs?: number;
  /** Optional WebSocket implementation (for tests). */
  WebSocketImpl?: typeof WebSocket;
}

function resolveWsUrl(explicit?: string): string {
  if (explicit) return explicit;
  const envUrl =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_WS_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
      : undefined;
  const base = envUrl ?? "http://localhost:8000";
  const wsBase = base.replace(/^http/, "ws").replace(/\/$/, "");
  return `${wsBase}/ws/stream`;
}

export function createWsClient(options: WsClientOptions = {}) {
  const url = resolveWsUrl(options.url);
  const minDelayMs = options.minDelayMs ?? 1000;
  const maxDelayMs = options.maxDelayMs ?? 30000;
  const pingIntervalMs = options.pingIntervalMs ?? 15000;
  const WebSocketCtor: typeof WebSocket | undefined =
    options.WebSocketImpl ??
    (typeof WebSocket !== "undefined" ? WebSocket : undefined);

  const listeners: Record<WsEventType, Set<AnyListener>> = {
    account_update: new Set(),
    position_update: new Set(),
    decision_update: new Set(),
    // Phase 8.5a (plan v3 G-5): multi-agent orchestrator degradation surface.
    orchestrator_error: new Set(),
  };
  const stateListeners = new Set<(s: ConnectionState) => void>();

  let ws: WebSocket | null = null;
  let state: ConnectionState = "idle";
  let attempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let lastDisconnectAt: number | null = null;
  let manualDisconnect = false;

  function setState(next: ConnectionState) {
    state = next;
    for (const cb of stateListeners) cb(next);
  }

  function clearPing() {
    if (pingTimer !== null) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  function scheduleReconnect() {
    if (manualDisconnect) return;
    if (reconnectTimer !== null) return;
    const base = Math.min(maxDelayMs, minDelayMs * 2 ** Math.min(attempts, 10));
    const jitter = Math.random() * 0.2 * base;
    const delay = Math.round(base + jitter);
    attempts += 1;
    setState("reconnecting");
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  function connect() {
    if (!WebSocketCtor) {
      // SSR / no WS available — no-op.
      return;
    }
    if (ws && (ws.readyState === WebSocketCtor.OPEN || ws.readyState === WebSocketCtor.CONNECTING)) {
      return;
    }
    manualDisconnect = false;
    setState("connecting");
    const socket = new WebSocketCtor(url);
    ws = socket;

    socket.onopen = () => {
      attempts = 0;
      lastDisconnectAt = null;
      setState("open");
      if (pingIntervalMs > 0) {
        clearPing();
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocketCtor.OPEN) {
            try {
              socket.send("ping");
            } catch {
              /* ignore — next onclose handles reconnect */
            }
          }
        }, pingIntervalMs);
      }
    };

    socket.onmessage = (ev: MessageEvent) => {
      const raw = typeof ev.data === "string" ? ev.data : "";
      if (!raw || raw === "pong") return;
      let env: WsEnvelope<unknown>;
      try {
        env = JSON.parse(raw) as WsEnvelope<unknown>;
      } catch {
        return;
      }
      const bucket = listeners[env.type as WsEventType];
      if (!bucket) return;
      for (const cb of bucket) cb(env);
    };

    socket.onclose = () => {
      clearPing();
      ws = null;
      lastDisconnectAt = Date.now();
      if (manualDisconnect) {
        setState("closed");
        return;
      }
      scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose is always fired after onerror for close-in-connect failures.
    };
  }

  function disconnect() {
    manualDisconnect = true;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    clearPing();
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      ws = null;
    }
    setState("closed");
  }

  function subscribe<T extends WsEventType>(type: T, cb: WsListener<T>): () => void {
    listeners[type].add(cb as AnyListener);
    return () => {
      listeners[type].delete(cb as AnyListener);
    };
  }

  function onStateChange(cb: (s: ConnectionState) => void): () => void {
    stateListeners.add(cb);
    // deliver current state synchronously so the listener is always consistent
    cb(state);
    return () => {
      stateListeners.delete(cb);
    };
  }

  return {
    connect,
    disconnect,
    subscribe,
    onStateChange,
    get state() {
      return state;
    },
    get lastDisconnectAt() {
      return lastDisconnectAt;
    },
  };
}

export type WsClient = ReturnType<typeof createWsClient>;
