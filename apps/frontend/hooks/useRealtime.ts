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
  RunPausedPayload,
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
  // T9 — most recent paused-run prompt (an above-threshold open
  // awaiting operator approval). Cleared when ApprovalBanner posts to
  // /confirm or /reject.
  const [pausedRun, setPausedRun] = useState<RunPausedPayload | null>(null);

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
    const mutateHistory = () =>
      globalMutate((key) => typeof key === "string" && key.startsWith("/api/history"));
    const mutateRebate = () => globalMutate("/api/v1/rebate");

    const unsubAccount = client.subscribe("account_update", (env) => {
      pushLog(env);
      globalMutate(ACCOUNT_KEY);
      mutateStats();
      // Equity sparkline shares the account snapshot cadence — every
      // recorder tick writes one history row, so refresh the chart on
      // the same SSE beat instead of polling.
      mutateHistory();
    });
    const unsubPosition = client.subscribe("position_update", (env) => {
      pushLog(env);
      globalMutate(POSITIONS_KEY);
      // mark_sync_batch (15s tick) and open events don't move trades or
      // rebate; only close + partial_close carry a Trade row + new fee.
      const action = (env.payload as { action?: string } | null)?.action;
      if (action === "close" || action === "partial_close") {
        mutateTrades();
        mutateRebate();
      } else if (action === "open") {
        mutateTrades();
      }
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
    const unsubRunPaused = client.subscribe("run_paused", (env) => {
      pushLog(env);
      setPausedRun(env.payload as RunPausedPayload);
    });

    const unsubState = client.onStateChange((s) => {
      setState(s);
      setLastDisconnectAt(client.lastDisconnectAt);
    });

    return () => {
      unsubAccount();
      unsubPosition();
      unsubDecision();
      unsubOrchestratorError();
      unsubRunPaused();
      unsubState();
    };
  }, [maxLog]);

  return {
    state,
    lastDisconnectAt,
    log,
    orchestratorError,
    lastDecisionEvent,
    pausedRun,
    clearPausedRun: () => setPausedRun(null),
  };
}
