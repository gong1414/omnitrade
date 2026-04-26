"use client";

import useSWR from "swr";
import { ConnectionBanner } from "@/components/ConnectionBanner";
import { AccountSummary } from "@/components/console/AccountSummary";
import { ConsoleHeader } from "@/components/console/ConsoleHeader";
import { ConsolePositionsTable } from "@/components/console/ConsolePositionsTable";
import { KpiStrip } from "@/components/console/KpiStrip";
import { PipelineRail } from "@/components/console/PipelineRail";
import { StrategyMini } from "@/components/console/StrategyMini";
import { TweaksPanel } from "@/components/console/TweaksPanel";
import { ReasoningStream } from "@/components/stream/ReasoningStream";
import { useDecisions } from "@/hooks/useDecisions";
import { useRealtime } from "@/hooks/useRealtime";
import { TweaksProvider } from "@/lib/console/tweaks";
import { apiClient } from "@/lib/api/client";
import type { ConfigResponse } from "@/lib/api/types";

const CONFIG_KEY = "/api/v1/config";

/**
 * OmniTrade Console — Agent Observatory dashboard.
 *
 * Layout (matches `OmniTrade Console.html` design mock):
 *   ┌─ ConsoleHeader (sticky) ───────────────────────────────┐
 *   │ ConnectionBanner (only on degraded WS)                 │
 *   ├─ KpiStrip (6 cells) ───────────────────────────────────┤
 *   │ ┌── Reasoning hero (1.35fr) ─┐ ┌── Right column ─┐     │
 *   │ │  ReasoningStream            │ │ AccountSummary  │     │
 *   │ │  (DecisionCards inline)     │ │ StrategyMini    │     │
 *   │ │                             │ │ PipelineRail    │     │
 *   │ └─────────────────────────────┘ └─────────────────┘     │
 *   ├─ ConsolePositionsTable (full width) ───────────────────┤
 *   └─ TweaksPanel (floating, bottom-right) ─────────────────┘
 */
export default function DashboardPage() {
  const { state, lastDisconnectAt, orchestratorError, lastDecisionEvent } = useRealtime();
  const { decisions } = useDecisions({ limit: 1 });
  const { data: config } = useSWR<ConfigResponse>(
    CONFIG_KEY,
    () => apiClient.fetchConfig(),
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );

  const intervalMin = config?.trading_interval_minutes ?? null;
  const initialBalance = config?.initial_balance_usdt ? Number(config.initial_balance_usdt) : null;
  const latestIteration = decisions[0]?.iteration ?? null;

  return (
    <TweaksProvider>
      <main className="console-shell min-h-screen">
        <ConsoleHeader intervalMin={intervalMin} state={state} />

        {(state !== "open" || orchestratorError) && (
          <div className="px-6 pt-4">
            <ConnectionBanner
              state={state}
              lastDisconnectAt={lastDisconnectAt}
              orchestratorError={orchestratorError}
            />
          </div>
        )}

        <div className="px-6 py-5 space-y-5">
          <KpiStrip initialBalance={initialBalance} />

          <div
            className="grid gap-5"
            style={{
              gridTemplateColumns:
                "minmax(0, 1.35fr) minmax(360px, 0.95fr)",
            }}
          >
            <ReasoningStream />

            <div className="space-y-5">
              <AccountSummary />
              <StrategyMini />
              <PipelineRail
                lastDecisionEvent={lastDecisionEvent}
                iteration={latestIteration}
              />
            </div>
          </div>

          <ConsolePositionsTable maxPos={config?.max_positions ?? null} />
        </div>

        <TweaksPanel />
      </main>
    </TweaksProvider>
  );
}
