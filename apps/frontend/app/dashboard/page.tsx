"use client";

import { AccountCard } from "@/components/AccountCard";
import { AgentReasoningFeed } from "@/components/AgentReasoningFeed";
import { ConnectionBanner } from "@/components/ConnectionBanner";
import { EquityChart } from "@/components/EquityChart";
import { HeaderStrip } from "@/components/HeaderStrip";
import { LocaleToggle } from "@/components/LocaleToggle";
import { LogStream } from "@/components/LogStream";
import { PipelineStatus } from "@/components/PipelineStatus";
import { PositionsTable } from "@/components/PositionsTable";
import { SessionMeta } from "@/components/SessionMeta";
import { StrategyPanel } from "@/components/StrategyPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TradesTable } from "@/components/TradesTable";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function DashboardPage() {
  const { state, lastDisconnectAt, log, orchestratorError } = useWebSocket();

  return (
    <main className="min-h-screen">
      <HeaderStrip state={state} />

      {(state !== "open" || orchestratorError) && (
        <div className="px-6 pt-4">
          <ConnectionBanner
            state={state}
            lastDisconnectAt={lastDisconnectAt}
            orchestratorError={orchestratorError}
          />
        </div>
      )}

      <div className="px-6 py-5">
        <PipelineStatus />
      </div>

      <div
        className="px-6 pb-10 grid gap-5"
        style={{
          gridTemplateColumns: "minmax(280px, 320px) minmax(0, 1fr) minmax(380px, 460px)",
        }}
      >
        <aside className="flex flex-col gap-5">
          <AccountCard />
          <StrategyPanel />
          <SessionMeta state={state} lastDisconnectAt={lastDisconnectAt} />
          <div className="flex items-center justify-end gap-2">
            <LocaleToggle />
            <ThemeToggle />
          </div>
        </aside>

        <section className="flex flex-col gap-5 min-w-0">
          <EquityChart />
          <PositionsTable />
          <TradesTable />
        </section>

        <section className="flex flex-col gap-5 min-w-0">
          <AgentReasoningFeed />
          <LogStream log={log} />
        </section>
      </div>
    </main>
  );
}
