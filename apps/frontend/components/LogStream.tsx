"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { cn, fmtTime } from "@/lib/utils";
import type { WsLogEntry } from "@/hooks/useWebSocket";
import type { WsEventType } from "@/lib/api/types";

const FILTERS: ("all" | WsEventType)[] = [
  "all",
  "account_update",
  "position_update",
  "decision_update",
  "orchestrator_error",
];

const toneFor: Record<WsEventType, "success" | "info" | "warn" | "danger"> = {
  account_update: "success",
  position_update: "info",
  decision_update: "warn",
  orchestrator_error: "danger",
};

export function LogStream({ log }: { log: WsLogEntry[] }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const visible = filter === "all" ? log : log.filter((e) => e.type === filter);

  return (
    <Card data-testid="logstream-card">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Live Events</CardTitle>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded px-2 py-0.5 text-[10px] uppercase tracking-wide transition-colors",
                filter === f
                  ? "bg-neutral-800 text-neutral-100"
                  : "text-neutral-500 hover:text-neutral-300",
              )}
            >
              {f === "all" ? "all" : f.split("_")[0]}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {visible.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">Waiting for events…</div>
        ) : (
          <ul className="max-h-[300px] overflow-y-auto divide-y divide-neutral-900">
            {visible.map((entry) => (
              <li
                key={entry.id}
                className="px-4 py-2 text-xs"
                data-testid="log-row"
                data-log-type={entry.type}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone={toneFor[entry.type]}>{entry.type.split("_")[0]}</Badge>
                    <span className="text-neutral-500">{fmtTime(entry.ts)}</span>
                  </div>
                  <span className="text-[10px] text-neutral-600 truncate max-w-[180px]">
                    {entry.trace_id}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
