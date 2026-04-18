import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  eyebrow?: ReactNode;
  title?: ReactNode;
  actions?: ReactNode;
  flush?: boolean;
}

/**
 * Observatory Panel — the single surface primitive for the control deck.
 * The eyebrow (uppercase mono) + serif display title pairing is what makes
 * the aesthetic cohesive; every section in the dashboard goes through here.
 */
export function Panel({
  eyebrow,
  title,
  actions,
  flush = false,
  className,
  children,
  ...rest
}: PanelProps) {
  return (
    <section
      className={cn(
        "relative overflow-hidden",
        "bg-obs-panel/70 backdrop-blur-[2px]",
        "border border-obs-line",
        "shadow-[0_1px_0_0_rgba(255,255,255,0.02)_inset]",
        className,
      )}
      {...rest}
    >
      {(eyebrow || title || actions) && (
        <header className="flex items-end justify-between gap-4 px-5 pt-4 pb-3 border-b border-obs-line-soft">
          <div className="min-w-0">
            {eyebrow ? (
              <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-obs-text-ghost">
                {eyebrow}
              </p>
            ) : null}
            {title ? (
              <h3 className="mt-0.5 font-display text-[20px] leading-tight text-obs-text">
                {title}
              </h3>
            ) : null}
          </div>
          {actions ? (
            <div className="shrink-0 flex items-center gap-1.5">{actions}</div>
          ) : null}
        </header>
      )}
      <div className={cn(flush ? "" : "p-5")}>{children}</div>
    </section>
  );
}

export function Chip({
  tone = "neutral",
  className,
  children,
}: {
  tone?: "neutral" | "green" | "amber" | "coral" | "violet" | "blue";
  className?: string;
  children: ReactNode;
}) {
  const palette: Record<string, string> = {
    neutral: "text-obs-text-dim border-obs-line bg-obs-panel-2/50",
    green: "text-obs-green border-obs-green/40 bg-obs-green/[0.08]",
    amber: "text-obs-amber border-obs-amber/40 bg-obs-amber/[0.08]",
    coral: "text-obs-coral border-obs-coral/40 bg-obs-coral/[0.08]",
    violet: "text-obs-violet border-obs-violet/40 bg-obs-violet/[0.08]",
    blue: "text-obs-blue border-obs-blue/40 bg-obs-blue/[0.08]",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 border px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.18em]",
        palette[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({
  tone = "neutral",
  breath = false,
  className,
}: {
  tone?: "neutral" | "green" | "amber" | "coral" | "violet";
  breath?: boolean;
  className?: string;
}) {
  const color: Record<string, string> = {
    neutral: "bg-obs-text-ghost",
    green: "bg-obs-green shadow-obs-pulse-green",
    amber: "bg-obs-amber shadow-obs-pulse-amber",
    coral: "bg-obs-coral shadow-obs-pulse-coral",
    violet: "bg-obs-violet",
  };
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block h-[7px] w-[7px] rounded-full",
        color[tone],
        breath ? "obs-breath" : "",
        className,
      )}
    />
  );
}
