"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { RebateSummary } from "@/lib/api/types";

export const REBATE_KEY = "/api/v1/rebate";

export function useRebate() {
  const { data, error, isLoading, mutate } = useSWR<RebateSummary>(
    REBATE_KEY,
    () => apiClient.fetchRebate(),
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );
  return { rebate: data, error, isLoading, mutate };
}
