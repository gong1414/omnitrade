"use client";

import { useEffect, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { apiClient, ApiError } from "@/lib/api/client";
import { useTranslations } from "@/lib/i18n/context";
import type { ConnectionState } from "@/lib/sse/client";

interface ConsoleHeaderProps {
  intervalMin: number | null;
  state: ConnectionState;
}

/**
 * Console-design header: brand mark + testnet pill + live dot + iter # +
 * next-cycle countdown + Run-cycle CTA + UTC clock. Replaces the legacy
 * HeaderStrip inside the Console dashboard only.
 */
export function ConsoleHeader({ intervalMin, state }: ConsoleHeaderProps) {
  const t = useTranslations();
  const tc = useTranslations("common");
  const { decisions, mutate: mutateDecisions } = useDecisions({ limit: 1 });

  const [now, setNow] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const period = (intervalMin ?? 20) * 60;
  const remaining = now
    ? period - (Math.floor(now.getTime() / 1000) % period)
    : 0;
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;

  async function onTrigger() {
    setBusy(true);
    setTriggerMsg(null);
    try {
      const res = await apiClient.triggerCycle();
      setTriggerMsg(t("header.cycle.ok", { sec: res.elapsed_seconds.toFixed(1) }));
      await mutateDecisions();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setTriggerMsg(t("header.cycle.busy"));
      else if (e instanceof ApiError && e.status === 503) setTriggerMsg(t("header.cycle.disabled"));
      else setTriggerMsg(t("header.cycle.error"));
    } finally {
      setBusy(false);
      setTimeout(() => setTriggerMsg(null), 4000);
    }
  }

  const liveTone =
    state === "open" ? "var(--obs-green)" : state === "reconnecting" ? "var(--cd-accent)" : "var(--obs-coral)";
  const liveLabel = t(`cd.header.${state === "open" ? "live" : "degraded"}`);

  return (
    <header
      className="sticky top-0 z-10 border-b backdrop-blur"
      style={{
        borderColor: "var(--obs-line)",
        background: "color-mix(in oklab, var(--obs-ink) 80%, transparent)",
      }}
    >
      <div className="px-6 py-3 flex items-center gap-5">
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center font-mono text-[14px] font-semibold"
            style={{ background: "var(--cd-accent)", color: "var(--obs-ink)" }}
          >
            ◆
          </div>
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-tight">
              {t("cd.brand.name")}
            </div>
            <div
              className="text-[10.5px] uppercase tracking-[0.16em] font-mono"
              style={{ color: "var(--cd-text-mute)" }}
            >
              {t("cd.brand.subtitle")}
            </div>
          </div>
        </div>

        <span className="h-5 w-px mx-1" style={{ background: "var(--obs-line)" }} />

        <span
          className="px-2 py-0.5 rounded text-[10px] uppercase tracking-[0.18em] font-mono"
          style={{ color: "var(--cd-accent)", background: "var(--cd-accent-soft)" }}
        >
          {t("cd.header.testnet")}
        </span>

        <div
          className="flex items-center gap-1.5 text-[11px] font-mono"
          style={{ color: "var(--obs-text-dim)" }}
        >
          <span
            className="cd-pulse-dot relative inline-block w-1.5 h-1.5 rounded-full"
            style={{ color: liveTone, background: liveTone }}
          />
          <span className="uppercase tracking-[0.14em]">{liveLabel}</span>
        </div>

        <div className="ml-auto flex items-center gap-5">
          <div
            className="text-[11px] font-mono tabular-nums"
            style={{ color: "var(--cd-text-mute)" }}
          >
            {t("cd.header.iter")}{" "}
            <span style={{ color: "var(--obs-text)" }}>
              #{decisions[0]?.iteration ?? "—"}
            </span>
          </div>
          <div
            className="text-[11px] font-mono tabular-nums flex items-center gap-1.5"
            style={{ color: "var(--cd-text-mute)" }}
          >
            <span>{t("cd.header.next_cycle")}</span>
            <span style={{ color: "var(--obs-text)" }} suppressHydrationWarning>
              {now ? `${m}:${String(s).padStart(2, "0")}` : "--:--"}
            </span>
          </div>
          <button
            onClick={onTrigger}
            disabled={busy}
            data-testid="cycle-trigger-btn"
            className="px-3 py-1.5 rounded-md text-[12px] font-medium border transition-colors disabled:opacity-40"
            style={{
              borderColor: "var(--cd-accent)",
              color: busy ? "var(--cd-text-mute)" : "var(--cd-accent)",
              background: "transparent",
            }}
            title={triggerMsg ?? t("header.cycle.title")}
            onMouseEnter={(e) => {
              if (!busy) (e.currentTarget.style.background = "var(--cd-accent-soft)");
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
            }}
          >
            {busy ? tc("loading") : `▸ ${t("cd.header.cycle")}`}
          </button>
          <span
            className="font-mono text-[11px] tabular-nums"
            style={{ color: "var(--cd-text-mute)" }}
            suppressHydrationWarning
          >
            {now ? now.toISOString().slice(11, 19) : "--:--:--"}{" "}
            <span style={{ color: "var(--cd-text-ghost)" }}>UTC</span>
          </span>
          {triggerMsg ? (
            <span
              data-testid="cycle-trigger-msg"
              className="text-[10px]"
              style={{ color: "var(--obs-text-dim)" }}
            >
              {triggerMsg}
            </span>
          ) : null}
        </div>
      </div>
    </header>
  );
}
