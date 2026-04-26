"use client";

import { useEffect, useState } from "react";
import { mutate as globalMutate } from "swr";
import { getSseClient } from "@/lib/sse/singleton";
import type { ConnectionState } from "@/lib/sse/client";
import { ACCOUNT_KEY } from "./useAccount";
import { POSITIONS_KEY } from "./usePositions";
import type {
  DecisionUpdatePayload,
  OrchestratorErrorPayload,
  WsEnvelope,
  WsEventType,
} from "@/lib/api/types";

export interface RealtimeLogEntry {
  id: number;
  type: WsEventType;
  ts: string;
  trace_id: string;
  payload: unknown;
}

let logCounter = 0;

export function useRealtime({ maxLog = 200 }: { maxLog?: number } = {}) {
  const [state, setState] = useState<ConnectionState>("idle");
  const [lastDisconnectAt, setLastDisconnectAt] = useState<number | null>(null);
  const [log, setLog] = useState<RealtimeLogEntry[]>([]);
  const [orchestratorError, setOrchestratorError] =
    useState<OrchestratorErrorPayload | null>(null);
  const [lastDecisionEvent, setLastDecisionEvent] =
    useState<WsEnvelope<DecisionUpdatePayload> | null>(null);

  useEffect(() => {
    const client = getSseClient();
    if (!client) return;

    const pushLog = (env: WsEnvelope<unknown>) => {
      logCounter += 1;
      setLog((prev) => {
        const next: RealtimeLogEntry[] = [
          { id: logCounter, type: env.type, ts: env.ts, trace_id: env.trace_id, payload: env.payload },
          ...prev,
        ];
        return next.slice(0, maxLog);
      });
    };

    const mutateTrades = () =>
      globalMutate((key) => typeof key === "string" && key.startsWith("/api/v1/trades"));
    const mutateStats = () => globalMutate("/api/stats");

    const unsubAccount = client.subscribe("account_update", (env) => {
      pushLog(env);
      globalMutate(ACCOUNT_KEY);
      mutateStats();
    });
    const unsubPosition = client.subscribe("position_update", (env) => {
      pushLog(env);
      globalMutate(POSITIONS_KEY);
      mutateTrades();
    });
    const unsubDecision = client.subscribe("decision_update", (env) => {
      pushLog(env);
      setLastDecisionEvent(env as WsEnvelope<DecisionUpdatePayload>);
      globalMutate((key) => typeof key === "string" && key.startsWith("/api/v1/decisions"));
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
