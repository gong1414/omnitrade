"use client";

import { useEffect, useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import { useTranslations } from "@/lib/i18n/context";
import type { ConnectionState } from "@/lib/ws/client";
import { Chip, StatusDot } from "./obs/Panel";

export function HeaderStrip({ state }: { state: ConnectionState }) {
  const { decisions } = useDecisions({ limit: 1 });
  const t = useTranslations("header");
  const [now, setNow] = useState<string | null>(null);

  useEffect(() => {
    setNow(new Date().toLocaleTimeString(undefined, { hour12: false }));
    const tick = setInterval(
      () => setNow(new Date().toLocaleTimeString(undefined, { hour12: false })),
      1000,
    );
    return () => clearInterval(tick);
  }, []);

  const wsTone: Parameters<typeof StatusDot>[0]["tone"] =
    state === "open" ? "green" : state === "reconnecting" ? "amber" : "coral";
  const wsLabel = t(`ws.${state === "open" ? "open" : state === "reconnecting" ? "reconnecting" : "closed"}`);

  return (
    <header className="flex items-center justify-between gap-6 border-b border-obs-line bg-obs-ink/70 px-6 py-4">
      <div className="flex items-center gap-4 min-w-0">
        <div>
          <h1 className="font-display text-[26px] font-black leading-none text-obs-text">
            {t("brand")}
            <span className="font-mono font-normal ml-2 text-[12px] uppercase tracking-[0.28em] text-obs-text-ghost">
              {t("tagline")}
            </span>
          </h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
            {t("subtitle")}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-6 font-mono text-[11px] tabular-nums">
        <span className="flex items-center gap-2">
          <StatusDot tone={wsTone} breath={state !== "open"} />
          <span className="text-obs-text-dim uppercase tracking-[0.18em] text-[10px]">
            {wsLabel}
          </span>
        </span>
        <span className="text-obs-text">
          {t("iter", { n: decisions[0]?.iteration ?? "—" })}
        </span>
        <span className="text-obs-text-dim" suppressHydrationWarning>
          {now ?? "--:--:--"} {t("utc").toLowerCase()}
        </span>
        <Chip tone="amber">{t("testnet")}</Chip>
      </div>
    </header>
  );
}
