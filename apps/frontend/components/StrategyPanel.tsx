"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import { Chip, Panel } from "./obs/Panel";

interface StrategyInfo {
  name?: string;
  interval_minutes?: number;
  max_leverage?: number;
  max_positions?: number;
  max_holding_hours?: number;
  extreme_stop_loss_percent?: number;
  initial_balance_usdt?: number;
}

// Use the same absolute base URL that apiClient.fetchAccount uses, so the
// browser talks straight to the backend (localhost:8000) instead of going
// through Next.js server-side rewrites (which point at the wrong host when
// the frontend container is reached from the user's host browser).
const STRATEGY_URL = `${
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
    : undefined) ?? "http://localhost:8000"
}/api/strategy`.replace(/\/$/, "");

const MINIMAL_BRANCH = new Set(["arena-autopilot", "arena-dual-signal"]);
const JURY_BRANCH = new Set(["arena-tribunal"]);
const TEAM_BRANCH = new Set(["arena-raider-squad"]);

function promptBranch(name?: string): { label: string; tone: Parameters<typeof Chip>[0]["tone"] } {
  if (!name) return { label: "—", tone: "neutral" };
  if (MINIMAL_BRANCH.has(name)) return { label: "Minimal prompt", tone: "violet" };
  if (JURY_BRANCH.has(name)) return { label: "3-juror consensus", tone: "blue" };
  if (TEAM_BRANCH.has(name)) return { label: "4-expert squad", tone: "blue" };
  return { label: "World-class trader", tone: "amber" };
}

export function StrategyPanel() {
  // Silence the unused-import linter for apiClient — we keep it imported so
  // the dev knows this panel shares its contract; the actual call goes via
  // STRATEGY_URL because `/api/strategy` has no prefix in the backend router.
  void apiClient;
  const { data } = useSWR<StrategyInfo>(
    STRATEGY_URL,
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`strategy fetch ${res.status}`);
      return res.json();
    },
    { refreshInterval: 15_000, revalidateOnFocus: false },
  );

  const branch = promptBranch(data?.name);

  return (
    <Panel eyebrow="Station · Strategy" title="Playbook" data-testid="strategy-panel">
      <div className="space-y-4">
        <div>
          <p className="font-mono text-[14px] text-obs-ftpink">
            {data?.name ?? "—"}
          </p>
          <div className="mt-1.5 flex items-center gap-1.5">
            <Chip tone={branch.tone}>{branch.label}</Chip>
          </div>
        </div>

        <div className="obs-hairline" />

        <dl className="grid grid-cols-2 gap-x-5 gap-y-2 font-mono text-[11px] tabular-nums">
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              Interval
            </dt>
            <dd className="text-obs-text">{data?.interval_minutes ?? "—"} min</dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              Max lev
            </dt>
            <dd className="text-obs-text">{data?.max_leverage ?? "—"}×</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              Max pos
            </dt>
            <dd className="text-obs-text">{data?.max_positions ?? "—"}</dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              Hold cap
            </dt>
            <dd className="text-obs-text">{data?.max_holding_hours ?? "—"} h</dd>
          </div>
          <div className="col-span-2 flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              Hard floor
            </dt>
            <dd className="text-obs-coral">
              {data?.extreme_stop_loss_percent !== undefined
                ? `${data.extreme_stop_loss_percent}% force-close`
                : "—"}
            </dd>
          </div>
        </dl>
      </div>
    </Panel>
  );
}
