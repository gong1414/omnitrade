import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Tone = "neutral" | "success" | "warn" | "danger" | "info";

const toneClass: Record<Tone, string> = {
  neutral: "bg-neutral-800 text-neutral-300 border-neutral-700",
  success: "bg-emerald-950 text-emerald-300 border-emerald-800",
  warn: "bg-amber-950 text-amber-300 border-amber-800",
  danger: "bg-red-950 text-red-300 border-red-800",
  info: "bg-sky-950 text-sky-300 border-sky-800",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        toneClass[tone],
        className,
      )}
      {...props}
    />
  );
}
