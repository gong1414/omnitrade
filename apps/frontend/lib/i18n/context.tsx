"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { locales, messages, type Locale, type MessageKey } from "./messages";

interface I18nCtx {
  locale: Locale;
  setLocale: (l: Locale) => void;
}

const Ctx = createContext<I18nCtx | null>(null);

const STORAGE_KEY = "omnitrade.locale";
const DEFAULT_LOCALE: Locale = "zh";

function detectInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const saved = window.localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (saved && locales.includes(saved)) return saved;
  const nav = window.navigator?.language ?? "";
  return nav.toLowerCase().startsWith("en") ? "en" : DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // Start in default so SSR and first client paint match; real value is
  // resolved in a mount effect to avoid hydration mismatches.
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setLocaleState(detectInitialLocale());
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    document.documentElement.lang = locale;
  }, [locale, mounted]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* localStorage blocked — in-memory state still carries the choice */
    }
  }, []);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLocale(): I18nCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLocale must be used inside <I18nProvider>");
  return ctx;
}

type Translator = (key: string, vars?: Record<string, string | number>) => string;

/**
 * useTranslations — returns a `t(key, vars)` function.
 *
 * Pass an optional `namespace` to avoid repeating the prefix; `t("title")`
 * inside `useTranslations("account")` resolves to `account.title`.
 */
export function useTranslations(namespace?: string): Translator {
  const { locale } = useLocale();
  const dict = messages[locale];
  const fallback = messages.en;
  return useCallback<Translator>(
    (key, vars) => {
      const full = (namespace ? `${namespace}.${key}` : key) as MessageKey;
      const raw = (dict[full] as string | undefined) ?? fallback[full] ?? full;
      if (!vars) return raw;
      let out = raw;
      for (const [k, v] of Object.entries(vars)) {
        out = out.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      }
      return out;
    },
    [dict, fallback, namespace],
  );
}
