import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "default" | "outline" | "ghost" | "destructive";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClass: Record<Variant, string> = {
  default:
    "bg-emerald-600 text-white hover:bg-emerald-500 focus-visible:ring-emerald-400",
  outline:
    "border border-neutral-700 bg-transparent text-neutral-100 hover:bg-neutral-800 focus-visible:ring-neutral-500",
  ghost:
    "bg-transparent text-neutral-300 hover:bg-neutral-800 focus-visible:ring-neutral-500",
  destructive:
    "bg-red-600 text-white hover:bg-red-500 focus-visible:ring-red-400",
};

const sizeClass: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "default", size = "md", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-neutral-950",
        "disabled:opacity-50 disabled:pointer-events-none",
        variantClass[variant],
        sizeClass[size],
        className,
      )}
      {...props}
    />
  );
});
