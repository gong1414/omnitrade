"use client";

import { useEffect, useState } from "react";
import { Badge } from "./ui/badge";
import type { ConnectionState } from "@/lib/ws/client";
import type { OrchestratorErrorPayload } from "@/lib/api/types";
import { useTranslations } from "@/lib/i18n/context";
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
  const t = useTranslations("banner");
  const th = useTranslations("header");
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  const disconnected = state !== "open";
  const durationMs =
    disconnected && lastDisconnectAt !== null ? now - lastDisconnectAt : 0;
  const showWarn = disconnected && durationMs > DISCONNECT_THRESHOLD_MS;
  const showOrchestratorError = orchestratorError !== null;

  if (!disconnected && !showOrchestratorError) {
    return (
      <div className="flex items-center gap-2 text-xs" data-testid="connection-banner">
        <Badge tone="success">{t("wsConnected")}</Badge>
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
            {th(`ws.${state === "reconnecting" ? "reconnecting" : "closed"}`)}
          </Badge>
          <span>
            {showWarn
              ? t("wsStale", { sec: Math.round(durationMs / 1000) })
              : t("wsOffline")}
          </span>
        </div>
      )}
      {showOrchestratorError && (
        <div
          className="flex items-center gap-2 rounded-md border border-red-800 bg-red-950/50 px-3 py-2 text-xs text-red-200"
          data-testid="orchestrator-error-banner"
          role="alert"
        >
          <Badge tone="danger">{t("orchestrator")}</Badge>
          <span>
            {t("orchestratorError", {
              strategy: orchestratorError!.strategy,
              reason: orchestratorError!.reason,
            })}
          </span>
        </div>
      )}
    </div>
  );
}
