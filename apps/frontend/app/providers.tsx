"use client";

import { ThemeProvider } from "next-themes";
import { SWRConfig } from "swr";
import { swrFetcher } from "@/lib/swr/fetcher";
import { I18nProvider } from "@/lib/i18n/context";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <I18nProvider>
        <SWRConfig
          value={{
            fetcher: swrFetcher,
            revalidateOnFocus: false,
            shouldRetryOnError: true,
            errorRetryCount: 3,
          }}
        >
          {children}
        </SWRConfig>
      </I18nProvider>
    </ThemeProvider>
  );
}
