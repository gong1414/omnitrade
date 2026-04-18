import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "700", "900"],
  style: ["normal", "italic"],
  variable: "--font-display",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-sans",
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
    fraunces.variable,
    plexMono.variable,
    plexSans.variable,
    "min-h-screen",
    "bg-obs-ink",
    "text-obs-text",
    "antialiased",
    "font-sans",
    "selection:bg-obs-violet/30",
  ].join(" ");
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={bodyClass}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
