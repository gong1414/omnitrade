"use client";

import { useEffect, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useHealth } from "@/hooks/useHealth";
import { usePositions } from "@/hooks/usePositions";
import { useTranslations } from "@/lib/i18n/context";
import type { ConnectionState } from "@/lib/sse/client";
import { Chip, Panel, StatusDot } from "./obs/Panel";

function formatUptime(ms: number): string {
  if (ms < 1000) return "0s";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function formatAgo(ts: string | undefined, now: number): string {
  if (!ts) return "—";
  const d = new Date(ts).getTime();
  if (Number.isNaN(d)) return "—";
  const delta = Math.max(0, now - d);
  return `${formatUptime(delta)} ago`;
}

export function SessionMeta({
  state,
  lastDisconnectAt,
}: {
  state: ConnectionState;
  lastDisconnectAt: number | null;
}) {
  const { decisions } = useDecisions({ limit: 1 });
  const { count: openPositions } = usePositions();
  const { health } = useHealth();
  const t = useTranslations("session");
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState<number>(0);
  // When the health poll arrives we snapshot (fetched-at, uptime-at-fetch)
  // so the tile can keep ticking locally between 30s polls without
  // drifting off the true backend uptime.
  const [healthAnchor, setHealthAnchor] = useState<
    { fetchedAt: number; uptimeMs: number } | null
  >(null);

  useEffect(() => {
    const start = Date.now();
    setNow(start);
    setMounted(true);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (!health) return;
    setHealthAnchor({
      fetchedAt: Date.now(),
      uptimeMs: Math.round(health.uptime_seconds * 1000),
    });
  }, [health]);

  const uptimeMs = healthAnchor
    ? healthAnchor.uptimeMs + (now - healthAnchor.fetchedAt)
    : null;

  const latest = decisions[0];
  const wsTone: Parameters<typeof StatusDot>[0]["tone"] =
    state === "open" ? "green" : state === "reconnecting" ? "amber" : "coral";

  return (
    <Panel eyebrow={t("eyebrow")} title={t("title")} data-testid="session-meta">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-obs-text-dim">
            <StatusDot tone={wsTone} breath={state !== "open"} />
            {t("stream", { state })}
          </span>
          <span
            className="font-mono text-[11px] tabular-nums text-obs-text"
            suppressHydrationWarning
          >
            {!mounted
              ? "—"
              : lastDisconnectAt && state !== "open"
                ? t("off", { duration: formatUptime(now - lastDisconnectAt) })
                : t("live")}
          </span>
        </div>

        <div className="obs-hairline" />

        <dl className="grid grid-cols-2 gap-x-5 gap-y-2 font-mono text-[11px] tabular-nums">
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("uptime")}
            </dt>
            <dd className="text-obs-text" suppressHydrationWarning>
              {mounted && uptimeMs !== null ? formatUptime(uptimeMs) : "—"}
            </dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("openPos")}
            </dt>
            <dd className="text-obs-text">{openPositions}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("iteration")}
            </dt>
            <dd className="text-obs-text">#{latest?.iteration ?? "—"}</dd>
          </div>
          <div className="flex flex-col text-right">
            <dt className="text-obs-text-ghost uppercase tracking-[0.18em] text-[9px]">
              {t("lastDecision")}
            </dt>
            <dd className="text-obs-text" suppressHydrationWarning>
              {mounted ? formatAgo(latest?.timestamp, now) : "—"}
            </dd>
          </div>
        </dl>

        <div className="mt-1 flex flex-wrap gap-1.5">
          <Chip tone="amber">{t("tagTestnet")}</Chip>
          <Chip tone="blue">{t("tagGate")}</Chip>
        </div>
      </div>
    </Panel>
  );
}
