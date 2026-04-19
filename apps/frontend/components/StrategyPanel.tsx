"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
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

// Absolute URL — avoid Next.js rewrites that point at the wrong host when
// the frontend container is reached from the user's host browser.
const STRATEGY_URL = `${
  (typeof process !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
    : undefined) ?? "http://localhost:8000"
}/api/strategy`.replace(/\/$/, "");

const MINIMAL_BRANCH = new Set(["arena-autopilot", "arena-dual-signal"]);
const JURY_BRANCH = new Set(["arena-tribunal"]);
const TEAM_BRANCH = new Set(["arena-raider-squad"]);

type Tone = Parameters<typeof Chip>[0]["tone"];

function branchKey(name?: string): { key: "minimal" | "jury" | "team" | "default"; tone: Tone } {
  if (!name) return { key: "default", tone: "neutral" };
  if (MINIMAL_BRANCH.has(name)) return { key: "minimal", tone: "violet" };
  if (JURY_BRANCH.has(name)) return { key: "jury", tone: "blue" };
  if (TEAM_BRANCH.has(name)) return { key: "team", tone: "blue" };
  return { key: "default", tone: "amber" };
}

export function StrategyPanel() {
  void apiClient;
  const t = useTranslations("strategy");
  const { data } = useSWR<StrategyInfo>(
    STRATEGY_URL,
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`strategy fetch ${res.status}`);
      return res.json();
    },
    { refreshInterval: 15_000, revalidateOnFocus: false },
  );

  const branch = branchKey(data?.name);

  return (
    <Panel eyebrow={t("eyebrow")} title={t("title")} data-testid="strategy-panel">
      <div className="space-y-4">
        <div>
          <p className="font-mono text-[14px] text-obs-ftpink">
            {data?.name ?? "—"}
          </p>
          <div className="mt-1.5 flex items-center gap-1.5">
            <Chip tone={branch.tone}>{t(`branch.${branch.key}`)}</Chip>
          </div>
        </div>

        <div className="obs-hairline" />

        <dl className="grid grid-cols-2 gap-x-5 gap-y-2 font-mono text-[11px] tabular-nums">
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("interval")}
            </dt>
            <dd className="text-obs-text">
              {data?.interval_minutes ?? "—"} {t("minUnit")}
            </dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("maxLev")}
            </dt>
            <dd className="text-obs-text">{data?.max_leverage ?? "—"}×</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("maxPos")}
            </dt>
            <dd className="text-obs-text">{data?.max_positions ?? "—"}</dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("holdCap")}
            </dt>
            <dd className="text-obs-text">
              {data?.max_holding_hours ?? "—"} {t("hourUnit")}
            </dd>
          </div>
          <div className="col-span-2 flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("hardFloor")}
            </dt>
            <dd className="text-obs-coral">
              {data?.extreme_stop_loss_percent !== undefined
                ? t("forceClose", { pct: data.extreme_stop_loss_percent })
                : "—"}
            </dd>
          </div>
        </dl>
      </div>
    </Panel>
  );
}
