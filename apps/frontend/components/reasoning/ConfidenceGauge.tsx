import { useTranslations } from "@/lib/i18n/context";

interface Props {
  value: number | null | undefined;
}

const RADIUS = 20;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function ConfidenceGauge({ value }: Props) {
  const t = useTranslations("reasoning");

  const pct = value != null ? Math.max(0, Math.min(1, value)) : 0;
  const dash = pct * CIRCUMFERENCE;
  const gap = CIRCUMFERENCE - dash;

  const color =
    pct >= 0.7 ? "#4ade80" : pct >= 0.4 ? "#fbbf24" : "#f87171";

  return (
    <div
      data-testid="reasoning-panel-confidence"
      className="mt-3 flex items-center gap-3"
    >
      <svg width="52" height="52" viewBox="0 0 52 52" aria-hidden>
        {/* track */}
        <circle
          cx="26"
          cy="26"
          r={RADIUS}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          className="text-obs-line"
        />
        {/* fill */}
        <circle
          cx="26"
          cy="26"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={`${dash} ${gap}`}
          strokeLinecap="round"
          transform="rotate(-90 26 26)"
        />
      </svg>
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-obs-text-ghost">
          {t("panel.confidence")}
        </span>
        <span className="font-mono text-[18px] tabular-nums text-obs-text" style={{ color }}>
          {value != null ? `${Math.round(pct * 100)}%` : "—"}
        </span>
      </div>
    </div>
  );
}
