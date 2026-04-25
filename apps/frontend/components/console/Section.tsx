"use client";

import type { ReactNode } from "react";

interface SectionProps {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  /** Disables the inner padding when child renders its own table or list. */
  flush?: boolean;
}

/**
 * Console-design Section frame: hairline-bordered surface with a tight header
 * row (title + optional subtitle + right-aligned action slot) above content.
 * Mirrors the `Section` primitive in the OmniTrade Console design mock.
 */
export function Section({ title, subtitle, action, children, flush }: SectionProps) {
  return (
    <section
      className="overflow-hidden rounded-lg border"
      style={{ borderColor: "var(--obs-line)", background: "var(--obs-panel)" }}
    >
      <header
        className="flex items-baseline gap-3 px-4 py-3 border-b"
        style={{ borderColor: "var(--obs-line)" }}
      >
        <h2 className="text-[13px] font-medium" style={{ color: "var(--obs-text)" }}>
          {title}
        </h2>
        {subtitle ? (
          <span
            className="text-[11px] truncate font-mono"
            style={{ color: "var(--cd-text-mute)" }}
          >
            {subtitle}
          </span>
        ) : null}
        {action ? <div className="ml-auto">{action}</div> : null}
      </header>
      <div className={flush ? "" : "px-4 py-3.5"}>{children}</div>
    </section>
  );
}

interface SparklineProps {
  points: Array<{ t: string; v: number }> | number[];
  width?: number;
  height?: number;
  color?: string;
}

/**
 * Filled-area sparkline, 100% width by default. Accepts either the
 * `{t, v}[]` shape from history endpoints or a plain `number[]`.
 */
export function Sparkline({
  points,
  width = 280,
  height = 48,
  color = "var(--cd-accent)",
}: SparklineProps) {
  const vals: number[] = Array.isArray(points)
    ? typeof points[0] === "number"
      ? (points as number[])
      : (points as Array<{ v: number }>).map((p) => p.v)
    : [];

  if (vals.length < 2) {
    return (
      <div
        className="h-12 w-full rounded"
        style={{ background: "var(--obs-panel-2)" }}
      />
    );
  }

  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const step = width / (vals.length - 1);
  const path = vals
    .map(
      (v, i) =>
        `${i === 0 ? "M" : "L"} ${(i * step).toFixed(2)} ${(height - ((v - min) / range) * height).toFixed(2)}`,
    )
    .join(" ");
  const area = `${path} L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block w-full" height={height}>
      <defs>
        <linearGradient id="cd-sparkfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#cd-sparkfill)" />
      <path d={path} fill="none" stroke={color} strokeWidth={1.25} />
    </svg>
  );
}
