"use client";

import { useDecisions } from "@/hooks/useDecisions";
import { fmtTime } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";

function summary(raw: string, max = 180): string {
  if (!raw) return "—";
  return raw.length > max ? `${raw.slice(0, max).trim()}…` : raw;
}

export function DecisionsFeed() {
  const { decisions, isLoading } = useDecisions({ limit: 25 });

  return (
    <Card data-testid="decisions-card">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Recent Decisions</CardTitle>
        <span className="text-xs text-neutral-500">{decisions.length}</span>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading && decisions.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">Loading…</div>
        ) : decisions.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">No decisions yet.</div>
        ) : (
          <ul className="divide-y divide-neutral-900 max-h-[400px] overflow-y-auto">
            {decisions.map((d) => (
              <li
                key={d.id}
                data-testid="decision-row"
                className="px-4 py-3 hover:bg-neutral-900/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge tone="info">#{d.iteration}</Badge>
                    <span className="text-xs text-neutral-500">{fmtTime(d.timestamp)}</span>
                  </div>
                  <span className="text-xs text-neutral-600 truncate max-w-[180px]">
                    {d.correlation_id ?? ""}
                  </span>
                </div>
                <p className="mt-2 text-sm text-neutral-200" data-testid="decision-text">
                  {summary(d.decision)}
                </p>
                <p className="mt-1 text-xs text-neutral-500">
                  {summary(d.market_analysis, 140)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
