import { useTranslations } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import type { AgentDecision } from "@/lib/api/types";

interface Props {
  decision: AgentDecision;
}

export function InvalidationCard({ decision }: Props) {
  const t = useTranslations("reasoning");

  return (
    <div
      data-testid="reasoning-panel-invalidation"
      className={cn(
        "mt-3 border border-obs-amber/30 bg-obs-amber/[0.04] px-3 py-2",
      )}
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-amber/70 mb-1">
        {t("panel.invalidation")}
      </p>
      <p className="font-sans text-[13px] leading-[1.55] text-obs-text/80">
        {decision.invalidation_condition || t("invalidation.empty")}
      </p>
    </div>
  );
}
