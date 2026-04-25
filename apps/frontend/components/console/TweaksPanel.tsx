"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "@/lib/i18n/context";
import type { Locale } from "@/lib/i18n/messages";
import { ACCENTS, useTweaks, type AccentName, type Density } from "@/lib/console/tweaks";

const ACCENT_OPTIONS: AccentName[] = ["claude", "indigo", "sage", "plum"];

/**
 * Console-design floating tweaks panel — bottom-right, glassy, draggable
 * via header. Carries: locale (proxies to existing I18n context),
 * accent, density, show-thinking, show-tools toggles. Closed by default;
 * a small "tweaks" pill in the corner toggles it open.
 */
export function TweaksPanel() {
  const t = useTranslations();
  const { locale, setLocale } = useLocale();
  const { tweaks, setTweak } = useTweaks();
  const [open, setOpen] = useState(false);
  const offsetRef = useRef({ x: 16, y: 16 });
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Persist open/closed state for the session
  useEffect(() => {
    const saved = window.sessionStorage.getItem("omnitrade.console.tweaks.open");
    if (saved === "1") setOpen(true);
  }, []);
  useEffect(() => {
    window.sessionStorage.setItem("omnitrade.console.tweaks.open", open ? "1" : "0");
  }, [open]);

  const onDragStart = (e: React.MouseEvent<HTMLDivElement>) => {
    const panel = panelRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX;
    const sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = (ev: MouseEvent) => {
      offsetRef.current = {
        x: Math.max(8, startRight - (ev.clientX - sx)),
        y: Math.max(8, startBottom - (ev.clientY - sy)),
      };
      panel.style.right = `${offsetRef.current.x}px`;
      panel.style.bottom = `${offsetRef.current.y}px`;
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-40 rounded-md border px-3 py-1.5 text-[11px] font-mono uppercase tracking-[0.14em]"
        style={{
          background: "var(--obs-panel)",
          color: "var(--cd-text-mute)",
          borderColor: "var(--obs-line)",
        }}
      >
        ⚙ {t("cd.tweaks.title")}
      </button>
    );
  }

  return (
    <div
      ref={panelRef}
      className="fixed z-40 w-[280px] rounded-xl overflow-hidden"
      style={{
        right: offsetRef.current.x,
        bottom: offsetRef.current.y,
        background: "color-mix(in oklab, var(--obs-panel) 88%, transparent)",
        backdropFilter: "blur(20px) saturate(160%)",
        WebkitBackdropFilter: "blur(20px) saturate(160%)",
        border: "1px solid var(--obs-line)",
        boxShadow: "0 12px 40px rgba(0,0,0,.35)",
      }}
    >
      <div
        className="flex items-center justify-between px-3.5 py-2.5 cursor-move select-none"
        onMouseDown={onDragStart}
      >
        <span className="text-[12px] font-medium" style={{ color: "var(--obs-text)" }}>
          {t("cd.tweaks.title")}
        </span>
        <button
          type="button"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={() => setOpen(false)}
          className="px-1.5 rounded text-[14px]"
          style={{ color: "var(--cd-text-mute)" }}
          aria-label="close tweaks"
        >
          ✕
        </button>
      </div>

      <div className="px-3.5 pb-3.5 space-y-3">
        <Field label={t("cd.tweaks.locale")}>
          <Segmented
            value={locale}
            options={[
              { value: "en", label: "EN" },
              { value: "zh", label: "中" },
            ]}
            onChange={(v) => setLocale(v as Locale)}
          />
        </Field>

        <Field label={t("cd.tweaks.accent")}>
          <Segmented
            value={tweaks.accent}
            options={ACCENT_OPTIONS.map((a) => ({
              value: a,
              label: a[0].toUpperCase() + a.slice(1),
              swatch: ACCENTS[a].accent,
            }))}
            onChange={(v) => setTweak("accent", v as AccentName)}
          />
        </Field>

        <Field label={t("cd.tweaks.density")}>
          <Segmented
            value={tweaks.density}
            options={[
              { value: "cozy", label: t("cd.tweaks.density.cozy") },
              { value: "compact", label: t("cd.tweaks.density.compact") },
            ]}
            onChange={(v) => setTweak("density", v as Density)}
          />
        </Field>

        <Toggle
          label={t("cd.tweaks.show_thinking")}
          checked={tweaks.showThinking}
          onChange={(v) => setTweak("showThinking", v)}
        />
        <Toggle
          label={t("cd.tweaks.show_tools")}
          checked={tweaks.showTools}
          onChange={(v) => setTweak("showTools", v)}
        />
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span
        className="text-[10px] uppercase tracking-[0.16em] font-mono"
        style={{ color: "var(--cd-text-ghost)" }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: Array<{ value: string; label: string; swatch?: string }>;
  onChange: (v: string) => void;
}) {
  return (
    <div
      className="flex rounded-md p-0.5 gap-0.5"
      style={{ background: "var(--obs-panel-2)" }}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className="flex-1 px-2 py-1 rounded text-[11px] font-medium flex items-center justify-center gap-1.5"
            style={{
              background: active ? "var(--obs-panel)" : "transparent",
              color: active ? "var(--obs-text)" : "var(--cd-text-mute)",
              boxShadow: active ? "0 1px 2px rgba(0,0,0,.25)" : "none",
            }}
          >
            {o.swatch ? (
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ background: o.swatch }}
              />
            ) : null}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11.5px]" style={{ color: "var(--obs-text-dim)" }}>
        {label}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className="relative w-8 h-[18px] rounded-full transition-colors"
        style={{ background: checked ? "var(--cd-accent)" : "var(--obs-line)" }}
      >
        <span
          className="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full transition-transform"
          style={{
            background: "var(--obs-text)",
            transform: checked ? "translateX(14px)" : "translateX(0)",
          }}
        />
      </button>
    </div>
  );
}
