import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obs: {
          ink: "var(--obs-ink)",
          panel: "var(--obs-panel)",
          "panel-2": "var(--obs-panel-2)",
          line: "var(--obs-line)",
          "line-soft": "var(--obs-line-soft)",
          text: "var(--obs-text)",
          "text-dim": "var(--obs-text-dim)",
          "text-ghost": "var(--obs-text-ghost)",
          green: "var(--obs-green)",
          amber: "var(--obs-amber)",
          coral: "var(--obs-coral)",
          violet: "var(--obs-violet)",
          blue: "var(--obs-blue)",
          ftpink: "var(--obs-ftpink)",
        },
        // Legacy aliases so any remaining old components keep compiling.
        background: "var(--obs-ink)",
        foreground: "var(--obs-text)",
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-serif", "Georgia", "serif"],
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        "obs-pulse-green": "var(--obs-glow-green)",
        "obs-pulse-amber": "var(--obs-glow-amber)",
        "obs-pulse-coral": "var(--obs-glow-coral)",
      },
    },
  },
  plugins: [],
};

export default config;
