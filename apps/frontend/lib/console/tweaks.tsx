"use client";

/**
 * Console-design Tweaks state. Persists locally so the user's chosen accent /
 * density / show toggles stick across reloads. The locale tweak proxies to the
 * existing I18n provider, so the dashboard's language switcher and the tweaks
 * panel stay in sync.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AccentName = "claude" | "indigo" | "sage" | "plum";
export type Density = "cozy" | "compact";

export interface Tweaks {
  accent: AccentName;
  density: Density;
  showThinking: boolean;
  showTools: boolean;
}

const STORAGE_KEY = "omnitrade.console.tweaks";

const DEFAULTS: Tweaks = {
  accent: "claude",
  density: "cozy",
  showThinking: true,
  showTools: true,
};

export const ACCENTS: Record<AccentName, { accent: string; soft: string }> = {
  claude: { accent: "#d97757", soft: "rgba(217,119,87,0.14)" },
  indigo: { accent: "#7d8ad9", soft: "rgba(125,138,217,0.14)" },
  sage:   { accent: "#87a96b", soft: "rgba(135,169,107,0.14)" },
  plum:   { accent: "#b07ab0", soft: "rgba(176,122,176,0.14)" },
};

interface TweaksCtxShape {
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => void;
}

const Ctx = createContext<TweaksCtxShape | null>(null);

function applyAccent(name: AccentName) {
  if (typeof document === "undefined") return;
  const a = ACCENTS[name] ?? ACCENTS.claude;
  document.documentElement.style.setProperty("--cd-accent", a.accent);
  document.documentElement.style.setProperty("--cd-accent-soft", a.soft);
  document.documentElement.style.setProperty("--obs-amber", a.accent);
  document.documentElement.style.setProperty("--obs-ftpink", a.accent);
}

export function TweaksProvider({ children }: { children: ReactNode }) {
  const [tweaks, setTweaks] = useState<Tweaks>(DEFAULTS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<Tweaks>;
        setTweaks((prev) => ({ ...prev, ...parsed }));
      }
    } catch {
      /* storage blocked → in-memory state still carries the choice */
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tweaks));
    } catch {
      /* ignore */
    }
    applyAccent(tweaks.accent);
  }, [tweaks, hydrated]);

  const setTweak = useCallback<TweaksCtxShape["setTweak"]>((key, value) => {
    setTweaks((prev) => ({ ...prev, [key]: value }));
  }, []);

  const value = useMemo(() => ({ tweaks, setTweak }), [tweaks, setTweak]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTweaks(): TweaksCtxShape {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTweaks must be used inside <TweaksProvider>");
  return ctx;
}
