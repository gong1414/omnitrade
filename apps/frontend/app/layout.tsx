import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// Console design pairing (OmniTrade · Agent Observatory):
//   - Inter for UI surfaces
//   - JetBrains Mono for tabular numerals + tool-call code blocks
//   - Source Serif 4 for reasoning prose (italic Justification text)
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-prose",
});


export const metadata: Metadata = {
  title: "OmniTrade · Observatory",
  description: "LLM-driven crypto-futures arena · testnet control deck",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const bodyClass = [
    inter.variable,
    jetbrainsMono.variable,
    sourceSerif.variable,
    "min-h-screen",
    "bg-obs-ink",
    "text-obs-text",
    "antialiased",
    "font-sans",
    "selection:bg-obs-amber/25",
  ].join(" ");
  return (
    <html lang="zh" className="dark" suppressHydrationWarning>
      <body
        className={bodyClass}
        style={{
          // Legacy `font-display` callers (e.g. HeaderStrip) fall back to Inter.
          ["--font-display" as string]: "var(--font-sans)",
        }}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
