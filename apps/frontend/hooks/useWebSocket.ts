"use client";

import { useEffect, useState } from "react";
import { mutate as globalMutate } from "swr";
import { getWsClient } from "@/lib/ws/singleton";
import type { ConnectionState } from "@/lib/ws/client";
import { ACCOUNT_KEY } from "./useAccount";
import { POSITIONS_KEY } from "./usePositions";
import type {
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  WsEnvelope,
  WsEventType,
} from "@/lib/api/types";

export interface WsLogEntry {
  id: number;
  type: WsEventType;
  ts: string;
  trace_id: string;
  payload: unknown;
}

let logCounter = 0;

export function useWebSocket({ maxLog = 200 }: { maxLog?: number } = {}) {
  const [state, setState] = useState<ConnectionState>("idle");
  const [lastDisconnectAt, setLastDisconnectAt] = useState<number | null>(null);
  const [log, setLog] = useState<WsLogEntry[]>([]);
  // Phase 8.5a (plan v3 G-5): surface the most recent multi-agent orchestrator
  // degradation to ConnectionBanner. `null` = no current error.
  const [orchestratorError, setOrchestratorError] =
    useState<OrchestratorErrorPayload | null>(null);
  // Task 5c — expose the most recent decision_update envelope so
  // PipelineStatus can animate with real per-stage timings from the
  // backend instead of a hardcoded setTimeout ladder.
  const [lastDecisionEvent, setLastDecisionEvent] =
    useState<WsEnvelope<DecisionUpdatePayload> | null>(null);

  useEffect(() => {
    const client = getWsClient();
    if (!client) return;

    const pushLog = (env: WsEnvelope<unknown>) => {
      logCounter += 1;
      setLog((prev) => {
        const next: WsLogEntry[] = [
          { id: logCounter, type: env.type, ts: env.ts, trace_id: env.trace_id, payload: env.payload },
          ...prev,
        ];
        return next.slice(0, maxLog);
      });
    };

    // Cycle-completion events affect several SWR caches that aren't directly
    // keyed by the event type. Refresh them here so the dashboard doesn't
    // wait out the next 10-15s poll interval to show a fresh trade or
    // KPI recomputation.
    const mutateTrades = () =>
      globalMutate((key) => typeof key === "string" && key.startsWith("/api/v1/trades"));
    const mutateStats = () => globalMutate("/api/stats");

    const unsubAccount = client.subscribe("account_update", (env) => {
      pushLog(env);
      globalMutate(ACCOUNT_KEY);
      // Stats sharpe/return are computed from account_history — refresh when
      // a new snapshot lands.
      mutateStats();
    });
    const unsubPosition = client.subscribe("position_update", (env) => {
      pushLog(env);
      globalMutate(POSITIONS_KEY);
      // position_update fires for every open/close/partial_close and carries
      // a trade in its payload. Bounce the trades cache so TradesTable shows
      // the new row instantly instead of on the next 10s poll.
      mutateTrades();
    });
    const unsubDecision = client.subscribe("decision_update", (env) => {
      pushLog(env);
      setLastDecisionEvent(env as WsEnvelope<DecisionUpdatePayload>);
      // mutate every /decisions key variant (limit/offset) — SWR key-pattern mutate
      globalMutate((key) => typeof key === "string" && key.startsWith("/api/v1/decisions"));
      // A cycle just finished — win_rate / n_trades / sharpe probably moved.
      mutateStats();
    });
    const unsubOrchestratorError = client.subscribe(
      "orchestrator_error",
      (env) => {
        pushLog(env);
        setOrchestratorError(env.payload as OrchestratorErrorPayload);
      },
    );

    const unsubState = client.onStateChange((s) => {
      setState(s);
      setLastDisconnectAt(client.lastDisconnectAt);
    });

    return () => {
      unsubAccount();
      unsubPosition();
      unsubDecision();
      unsubOrchestratorError();
      unsubState();
    };
  }, [maxLog]);

  return { state, lastDisconnectAt, log, orchestratorError, lastDecisionEvent };
}
