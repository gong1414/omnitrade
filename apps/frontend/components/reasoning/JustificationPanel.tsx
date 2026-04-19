"use client";

import { useState } from "react";
import { useTranslations } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";

interface Props {
  text: string | null | undefined;
}

const PREVIEW_LEN = 260;

export function JustificationPanel({ text }: Props) {
  const t = useTranslations("reasoning");
  const [expanded, setExpanded] = useState(false);

  if (!text) return null;

  const isLong = text.length > PREVIEW_LEN;
  const shown = !expanded && isLong ? `${text.slice(0, PREVIEW_LEN).trim()}…` : text;

  return (
    <div
      data-testid="reasoning-panel-justification"
      className={cn(
        "mt-3 border border-obs-violet/30 bg-obs-violet/[0.04] px-3 py-2",
      )}
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-violet/70 mb-1">
        {t("panel.justification")}
      </p>
      <p className="whitespace-pre-wrap font-sans text-[13px] leading-[1.55] text-obs-text/85">
        {shown}
      </p>
      {isLong ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          data-testid="justification-toggle"
          className="mt-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-obs-violet hover:text-obs-text"
        >
          {expanded ? t("collapse") : t("expand")}
        </button>
      ) : null}
    </div>
  );
}
