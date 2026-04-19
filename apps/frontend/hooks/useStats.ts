"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { StatsResponse } from "@/lib/api/types";

export const STATS_KEY = "/api/stats";

export function useStats() {
  const { data, error, isLoading, mutate } = useSWR<StatsResponse>(
    STATS_KEY,
    () => apiClient.fetchStats(),
    { refreshInterval: 15_000, revalidateOnFocus: false },
  );
  return { stats: data, error, isLoading, mutate };
}
