"use client";

import { useLocale, useTranslations } from "@/lib/i18n/context";
import { localeLabels, locales } from "@/lib/i18n/messages";
import { Button } from "./ui/button";
import { cn } from "@/lib/utils";

export function LocaleToggle() {
  const { locale, setLocale } = useLocale();
  const t = useTranslations("common");
  return (
    <div
      className="inline-flex items-center gap-0.5 border border-obs-line bg-obs-panel/60 px-0.5"
      role="group"
      aria-label={t("switchLocale")}
    >
      {locales.map((l) => (
        <Button
          key={l}
          variant="ghost"
          size="sm"
          onClick={() => setLocale(l)}
          aria-pressed={locale === l}
          className={cn(
            "font-mono text-[10px] uppercase tracking-[0.18em] px-2 h-6",
            locale === l ? "text-obs-amber" : "text-obs-text-dim",
          )}
        >
          {localeLabels[l]}
        </Button>
      ))}
    </div>
  );
}
