"use client";

import { useEffect, useState } from "react";
import { Badge } from "./ui/badge";
import type { ConnectionState } from "@/lib/ws/client";
import type { OrchestratorErrorPayload } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const DISCONNECT_THRESHOLD_MS = 30_000;

export function ConnectionBanner({
  state,
  lastDisconnectAt,
  orchestratorError = null,
}: {
  state: ConnectionState;
  lastDisconnectAt: number | null;
  orchestratorError?: OrchestratorErrorPayload | null;
}) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const disconnected = state !== "open";
  const durationMs =
    disconnected && lastDisconnectAt !== null ? now - lastDisconnectAt : 0;
  const showWarn = disconnected && durationMs > DISCONNECT_THRESHOLD_MS;

  // Phase 8.5a (plan v3 G-5): multi-agent orchestrator degradation takes
  // priority over a transient disconnect — if both, render the orchestrator
  // error as a red warning banner below the connection state.
  const showOrchestratorError = orchestratorError !== null;

  if (!disconnected && !showOrchestratorError) {
    return (
      <div className="flex items-center gap-2 text-xs" data-testid="connection-banner">
        <Badge tone="success">WS connected</Badge>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid="connection-banner">
      {disconnected && (
        <div
          className={cn(
            "flex items-center gap-2 rounded-md border px-3 py-2 text-xs",
            showWarn
              ? "border-red-800 bg-red-950/50 text-red-200"
              : "border-amber-800 bg-amber-950/40 text-amber-200",
          )}
          role="status"
        >
          <Badge tone={showWarn ? "danger" : "warn"}>
            {state === "reconnecting" ? "reconnecting" : state}
          </Badge>
          <span>
            {showWarn
              ? `Disconnected ${Math.round(durationMs / 1000)}s — data may be stale`
              : "Live stream temporarily offline"}
          </span>
        </div>
      )}
      {showOrchestratorError && (
        <div
          className="flex items-center gap-2 rounded-md border border-red-800 bg-red-950/50 px-3 py-2 text-xs text-red-200"
          data-testid="orchestrator-error-banner"
          role="alert"
        >
          <Badge tone="danger">orchestrator</Badge>
          <span>
            Multi-agent orchestrator error: {orchestratorError!.strategy} —{" "}
            {orchestratorError!.reason}
          </span>
        </div>
      )}
    </div>
  );
}
