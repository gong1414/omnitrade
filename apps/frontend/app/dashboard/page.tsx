"use client";

import { AccountCard } from "@/components/AccountCard";
import { PositionsTable } from "@/components/PositionsTable";
import { DecisionsFeed } from "@/components/DecisionsFeed";
import { EquityChart } from "@/components/EquityChart";
import { LogStream } from "@/components/LogStream";
import { ConnectionBanner } from "@/components/ConnectionBanner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function DashboardPage() {
  const { state, lastDisconnectAt, log, orchestratorError } = useWebSocket();

  return (
    <main className="min-h-screen p-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-neutral-100">OmniTrade</h1>
          <p className="text-xs text-neutral-500">AI Trading Agent Dashboard</p>
        </div>
        <div className="flex items-center gap-4">
          <ConnectionBanner
            state={state}
            lastDisconnectAt={lastDisconnectAt}
            orchestratorError={orchestratorError}
          />
          <ThemeToggle />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1 space-y-4">
          <AccountCard />
          <EquityChart />
        </div>
        <div className="lg:col-span-2 space-y-4">
          <PositionsTable />
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <DecisionsFeed />
            <LogStream log={log} />
          </div>
        </div>
      </div>
    </main>
  );
}
