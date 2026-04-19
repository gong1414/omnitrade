"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import type { StrategyResponse } from "@/lib/api/types";
import { Chip, Panel } from "./obs/Panel";

const STRATEGY_KEY = "/api/strategy";

const MINIMAL_BRANCH = new Set(["arena-autopilot", "arena-dual-signal"]);
const JURY_BRANCH = new Set(["arena-tribunal"]);
const TEAM_BRANCH = new Set(["arena-raider-squad"]);

type Tone = Parameters<typeof Chip>[0]["tone"];

function branchKey(
  name?: string | null,
): { key: "minimal" | "jury" | "team" | "default"; tone: Tone } {
  if (!name) return { key: "default", tone: "neutral" };
  if (MINIMAL_BRANCH.has(name)) return { key: "minimal", tone: "violet" };
  if (JURY_BRANCH.has(name)) return { key: "jury", tone: "blue" };
  if (TEAM_BRANCH.has(name)) return { key: "team", tone: "blue" };
  return { key: "default", tone: "amber" };
}

export function StrategyPanel() {
  const t = useTranslations("strategy");
  const { data } = useSWR<StrategyResponse>(
    STRATEGY_KEY,
    () => apiClient.fetchStrategy(),
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
            {data?.multi_agent_enabled ? (
              <Chip tone="blue">{t("multiAgent")}</Chip>
            ) : null}
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
              {data?.extreme_stop_loss_percent != null
                ? t("forceClose", { pct: data.extreme_stop_loss_percent })
                : "—"}
            </dd>
          </div>
        </dl>
      </div>
    </Panel>
  );
}
