/**
 * Theme tokens — single source for spacing, radii, and semantic colors used
 * by hand-crafted primitives and chart components.
 */

export const theme = {
  colors: {
    bg: "#0a0a0a",
    bgElevated: "#111111",
    border: "#1f1f1f",
    text: "#ededed",
    textMuted: "#9a9a9a",
    accent: "#10b981",
    positive: "#10b981",
    negative: "#ef4444",
    warn: "#f59e0b",
    info: "#0ea5e9",
  },
  radii: {
    sm: "0.25rem",
    md: "0.375rem",
    lg: "0.5rem",
  },
  spacing: {
    xs: "0.25rem",
    sm: "0.5rem",
    md: "1rem",
    lg: "1.5rem",
    xl: "2rem",
  },
} as const;

export type Theme = typeof theme;
