"use client";

import { useEffect, useState } from "react";
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
import { fmtNum } from "@/lib/utils";

interface EquityPoint {
  ts: number;
  value: number;
}

const MAX_POINTS = 300;

export function EquityChart() {
  const { account } = useAccount();
  const [points, setPoints] = useState<EquityPoint[]>([]);

  useEffect(() => {
    if (!account) return;
    const ts = new Date(account.timestamp).getTime();
    const value = Number(account.total_value);
    if (Number.isNaN(ts) || Number.isNaN(value)) return;
    setPoints((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.ts === ts) return prev;
      const next = [...prev, { ts, value }];
      return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
    });
  }, [account]);

  const latest = points[points.length - 1]?.value;
  const first = points[0]?.value;
  const delta =
    latest !== undefined && first !== undefined && first !== 0
      ? ((latest - first) / first) * 100
      : 0;

  return (
    <Panel
      eyebrow="Floor · Equity"
      title="Session PnL"
      actions={
        latest !== undefined ? (
          <span className="font-mono text-[11px] tabular-nums">
            <span className="text-obs-text-dim">Δ</span>{" "}
            <span
              className={delta >= 0 ? "text-obs-green" : "text-obs-coral"}
            >
              {delta >= 0 ? "+" : ""}
              {fmtNum(delta, 2)}%
            </span>
          </span>
        ) : null
      }
      data-testid="equity-card"
    >
      <div className="h-[220px] -mx-3">
        {points.length < 2 ? (
          <div className="flex h-full items-center justify-center text-sm text-obs-text-dim">
            Accumulating live equity points…
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
                formatter={(value: number) => [`$${Number(value).toFixed(2)}`, "Balance"]}
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
