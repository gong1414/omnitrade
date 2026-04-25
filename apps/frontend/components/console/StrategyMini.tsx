"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import type { ConfigResponse, StrategyResponse } from "@/lib/api/types";
import { Section } from "./Section";

const STRATEGY_KEY = "/api/strategy";
const CONFIG_KEY = "/api/v1/config";

/**
 * Right-column Strategy panel. Strategy name + branch chip + multi-agent flag,
 * followed by 7 key/value pairs (interval / max_lev / max_pos / hold_cap /
 * hard_floor / venue / model). Reads `/api/strategy` for the live state and
 * `/api/v1/config` for venue + model name.
 */
export function StrategyMini() {
  const t = useTranslations();
  const { data: strategy } = useSWR<StrategyResponse>(
    STRATEGY_KEY,
    () => apiClient.fetchStrategy(),
    { refreshInterval: 15_000, revalidateOnFocus: false },
  );
  const { data: config } = useSWR<ConfigResponse>(
    CONFIG_KEY,
    () => apiClient.fetchConfig(),
    { refreshInterval: 30_000, revalidateOnFocus: false },
  );

  const venue = config?.exchange ?? "—";
  const venueSuffix =
    config?.gate_use_testnet === true || config?.okx_use_testnet === true ? " · testnet" : "";
  const model = config?.llm_model_name ?? "—";

  const rows: Array<[string, string]> = [
    [t("cd.strategy.interval"), strategy?.interval_minutes ? `${strategy.interval_minutes} min` : "—"],
    [t("cd.strategy.max_lev"), strategy?.max_leverage ? `${strategy.max_leverage}×` : "—"],
    [t("cd.strategy.max_pos"), strategy?.max_positions != null ? String(strategy.max_positions) : "—"],
    [t("cd.strategy.hold_cap"), strategy?.max_holding_hours ? `${strategy.max_holding_hours} h` : "—"],
    [t("cd.strategy.hard_floor"), strategy?.extreme_stop_loss_percent != null ? `${strategy.extreme_stop_loss_percent}%` : "—"],
    [t("cd.strategy.venue"), `${venue}${venueSuffix}`],
    [t("cd.strategy.model"), model],
  ];

  return (
    <Section title={t("cd.strategy.title")}>
      <div className="space-y-2.5">
        <div
          className="flex items-baseline gap-2 pb-2 border-b"
          style={{ borderColor: "var(--obs-line)" }}
        >
          <span className="text-[14px] font-medium" style={{ color: "var(--obs-text)" }}>
            {strategy?.name ?? "—"}
          </span>
          {strategy?.multi_agent_enabled ? (
            <span
              className="ml-auto text-[10px] uppercase tracking-[0.14em] font-mono"
              style={{ color: "var(--cd-accent)" }}
            >
              {t("cd.strategy.multi_agent")}
            </span>
          ) : null}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11.5px]">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <dt style={{ color: "var(--cd-text-ghost)" }}>{k}</dt>
              <dd
                className="truncate text-right tabular-nums"
                style={{ color: "var(--obs-text-dim)" }}
                title={v}
              >
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </Section>
  );
}
