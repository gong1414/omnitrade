import { useTranslations } from "@/lib/i18n/context";
import { Chip } from "@/components/obs/Panel";
import type { AgentDecision } from "@/lib/api/types";

interface Props {
  decision: AgentDecision;
}

export function GatesPanel({ decision }: Props) {
  const t = useTranslations("reasoning");

  return (
    <div
      data-testid="reasoning-panel-gates"
      className="mt-3 space-y-1.5"
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
        {t("panel.gates")}
      </p>
      {decision.gates_passed && decision.gates_passed.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {decision.gates_passed.map((gate, i) => (
            <Chip key={i} tone="green">
              {gate}
            </Chip>
          ))}
        </div>
      ) : (
        <p className="font-mono text-[11px] text-obs-text-dim">
          {t("gates.empty")}
        </p>
      )}
    </div>
  );
}
