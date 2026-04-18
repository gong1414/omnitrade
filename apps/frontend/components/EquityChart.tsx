"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { useAccount } from "@/hooks/useAccount";

interface EquityPoint {
  ts: number;
  value: number;
}

const MAX_POINTS = 300;

/**
 * Accumulates `account_update` snapshots over the session. Phase 5 does not
 * expose a historical-equity endpoint; Phase 6 treats this as a rolling
 * in-memory trail seeded by the SWR-polled current snapshot.
 */
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

  return (
    <Card data-testid="equity-card">
      <CardHeader>
        <CardTitle>Equity</CardTitle>
      </CardHeader>
      <CardContent className="h-[220px] p-2">
        {points.length < 2 ? (
          <div className="flex h-full items-center justify-center text-xs text-neutral-500">
            Waiting for data…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f1f1f" />
              <XAxis
                dataKey="ts"
                tickFormatter={(v) => new Date(v).toLocaleTimeString()}
                stroke="#525252"
                fontSize={10}
                minTickGap={40}
              />
              <YAxis
                stroke="#525252"
                fontSize={10}
                domain={["auto", "auto"]}
                tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
              />
              <Tooltip
                contentStyle={{ background: "#0a0a0a", border: "1px solid #1f1f1f", fontSize: 12 }}
                labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
                formatter={(value: number) => [`$${Number(value).toFixed(2)}`, "Balance"]}
              />
              <Line type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
