"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { HealthResponse } from "@/lib/api/types";

export const HEALTH_KEY = "/api/health";

export function useHealth() {
  const { data, error, isLoading } = useSWR<HealthResponse>(
    HEALTH_KEY,
    () => apiClient.getHealth(),
    {
      refreshInterval: 30_000,
      revalidateOnFocus: false,
      // health snapshot at mount — uptime_seconds is frozen at fetch
      // time, the frontend counts forward from there between polls so
      // the SessionMeta tile still ticks visually without hammering
      // the backend every second.
    },
  );
  return { health: data, error, isLoading };
}
