"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { useTranslations } from "@/lib/i18n/context";
import { Button } from "./ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const t = useTranslations("common");
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted)
    return (
      <Button variant="ghost" size="sm" aria-label={t("toggleTheme")}>
        …
      </Button>
    );
  const next = resolvedTheme === "dark" ? "light" : "dark";
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setTheme(next)}
      aria-label={t("switchTheme", { next })}
    >
      {resolvedTheme === "dark" ? "☾" : "☀"}
    </Button>
  );
}
