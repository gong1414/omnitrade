"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "./obs/Panel";
import { useAccount } from "@/hooks/useAccount";
import { useHistory } from "@/hooks/useHistory";
import { useTranslations } from "@/lib/i18n/context";
import { cn, fmtNum } from "@/lib/utils";
import type { HistoryWindow } from "@/lib/api/types";

interface EquityPoint {
  ts: number;
  value: number;
}

const MAX_POINTS = 600;
const WINDOWS: HistoryWindow[] = ["24h", "7d", "30d"];

export function EquityChart() {
  const { account } = useAccount();
  const t = useTranslations("equity");
  const [window, setWindow] = useState<HistoryWindow>("24h");
  const { history, isLoading } = useHistory(window);
  const [livePoints, setLivePoints] = useState<EquityPoint[]>([]);

  // Reset live tail when the window changes so we don't mix histories.
  useEffect(() => {
    setLivePoints([]);
  }, [window]);

  // Append newest account snapshot to the live tail (dedupe by timestamp).
  useEffect(() => {
    if (!account) return;
    const ts = new Date(account.timestamp).getTime();
    const value = Number(account.total_value);
    if (Number.isNaN(ts) || Number.isNaN(value)) return;
    setLivePoints((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.ts === ts) return prev;
      const next = [...prev, { ts, value }];
      return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
    });
  }, [account]);

  const points = useMemo<EquityPoint[]>(() => {
    const seeded: EquityPoint[] =
      history?.timestamps.map((iso, i) => ({
        ts: new Date(iso).getTime(),
        value: history.total_value[i],
      })) ?? [];
    const lastSeededTs = seeded[seeded.length - 1]?.ts ?? 0;
    const tail = livePoints.filter((p) => p.ts > lastSeededTs);
    const combined = [...seeded, ...tail];
    return combined.length > MAX_POINTS ? combined.slice(-MAX_POINTS) : combined;
  }, [history, livePoints]);

  const latest = points[points.length - 1]?.value;
  const first = points[0]?.value;
  const delta =
    latest !== undefined && first !== undefined && first !== 0
      ? ((latest - first) / first) * 100
      : 0;

  return (
    <Panel
      eyebrow={t("eyebrow")}
      title={t("title")}
      actions={
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => setWindow(w)}
                data-testid={`equity-window-${w}`}
                className={cn(
                  "px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.18em] border transition-colors",
                  window === w
                    ? "border-obs-amber/60 bg-obs-amber/10 text-obs-amber"
                    : "border-transparent text-obs-text-ghost hover:text-obs-text",
                )}
              >
                {t(`window.${w}`)}
              </button>
            ))}
          </div>
          {latest !== undefined ? (
            <span className="font-mono text-[11px] tabular-nums">
              <span className="text-obs-text-dim">Δ</span>{" "}
              <span className={delta >= 0 ? "text-obs-green" : "text-obs-coral"}>
                {delta >= 0 ? "+" : ""}
                {fmtNum(delta, 2)}%
              </span>
            </span>
          ) : null}
        </div>
      }
      data-testid="equity-card"
    >
      <div className="h-[220px] -mx-3">
        {points.length < 2 ? (
          <div className="flex h-full items-center justify-center text-sm text-obs-text-dim">
            {isLoading ? t("accumulating") : t("empty")}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="obsEquity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--obs-green)" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="var(--obs-green)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke="var(--obs-line)" />
              <XAxis
                dataKey="ts"
                tickFormatter={(v) =>
                  new Date(v).toLocaleTimeString(undefined, { hour12: false })
                }
                stroke="var(--obs-text-ghost)"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: "var(--obs-line)" }}
                minTickGap={48}
              />
              <YAxis
                stroke="var(--obs-text-ghost)"
                fontSize={10}
                domain={["auto", "auto"]}
                tickLine={false}
                axisLine={{ stroke: "var(--obs-line)" }}
                tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                width={52}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--obs-panel)",
                  border: "1px solid var(--obs-line)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  color: "var(--obs-text)",
                }}
                labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
                formatter={(value: number) => [`$${Number(value).toFixed(2)}`, t("balance")]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--obs-green)"
                strokeWidth={1.5}
                fill="url(#obsEquity)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
