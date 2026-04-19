import { useTranslations } from "@/lib/i18n/context";
import type { AgentDecision } from "@/lib/api/types";

interface Props {
  decision: AgentDecision;
}

export function MarketContextPanel({ decision }: Props) {
  const t = useTranslations("reasoning");

  if (!decision.market_context) return null;

  return (
    <div
      data-testid="reasoning-panel-market-context"
      className="mt-3 space-y-1"
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
        {t("panel.marketContext")}
      </p>
      <p className="font-sans text-[13px] leading-[1.55] text-obs-text/80">
        {decision.market_context}
      </p>
    </div>
  );
}
