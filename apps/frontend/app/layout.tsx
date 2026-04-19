import type { Metadata } from "next";
import { IBM_Plex_Mono, Lora, Poppins } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// Anthropic brand pairing: Poppins (display/headings) + Lora (body/serif).
// IBM Plex Mono is retained for tabular numerals and code-style metadata.
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-display",
});

const lora = Lora({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
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
    poppins.variable,
    lora.variable,
    plexMono.variable,
    "min-h-screen",
    "bg-obs-ink",
    "text-obs-text",
    "antialiased",
    "font-sans",
    "selection:bg-obs-amber/25",
  ].join(" ");
  return (
    <html suppressHydrationWarning>
      <body className={bodyClass}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
