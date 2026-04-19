import { useTranslations } from "@/lib/i18n/context";
import { fmtNum } from "@/lib/utils";
import type { AgentDecisionPlan } from "@/lib/api/types";

interface Props {
  plan: AgentDecisionPlan;
}

function PlanField({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-obs-text-ghost">
        {label}
      </span>
      <span className="font-mono text-[13px] tabular-nums text-obs-text">
        {value != null ? fmtNum(value, 2) : "—"}
      </span>
    </div>
  );
}

export function PlanCard({ plan }: Props) {
  const t = useTranslations("reasoning");

  return (
    <div
      data-testid="reasoning-panel-plan"
      className="mt-3 border border-obs-line px-3 py-2 space-y-2"
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
        {t("panel.plan")}
      </p>
      <div className="grid grid-cols-4 gap-3">
        <PlanField label={t("plan.entry")} value={plan.entry} />
        <PlanField label={t("plan.stopLoss")} value={plan.stop_loss} />
        <PlanField label={t("plan.takeProfit1")} value={plan.take_profit_1} />
        <PlanField label={t("plan.takeProfit2")} value={plan.take_profit_2} />
      </div>
      {(plan.risk_usd != null || plan.r_multiple_target != null) && (
        <div className="flex gap-6 pt-1 border-t border-obs-line-soft">
          {plan.risk_usd != null && (
            <div className="flex flex-col gap-0.5">
              <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-obs-text-ghost">
                {t("plan.riskUsd")}
              </span>
              <span className="font-mono text-[13px] tabular-nums text-obs-coral">
                ${fmtNum(plan.risk_usd, 2)}
              </span>
            </div>
          )}
          {plan.r_multiple_target != null && (
            <div className="flex flex-col gap-0.5">
              <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-obs-text-ghost">
                {t("plan.rMultiple")}
              </span>
              <span className="font-mono text-[13px] tabular-nums text-obs-green">
                {fmtNum(plan.r_multiple_target, 2)}R
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
