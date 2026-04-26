"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { RebateSummary } from "@/lib/api/types";

export const REBATE_KEY = "/api/v1/rebate";

export function useRebate() {
  const { data, error, isLoading, mutate } = useSWR<RebateSummary>(
    REBATE_KEY,
    () => apiClient.fetchRebate(),
    // SSE `position_update` with action ∈ {close, partial_close}
    // triggers a global mutate of this key, so a periodic poll would
    // only ever surface duplicates of the same window summary.
    { revalidateOnFocus: false },
  );
  return { rebate: data, error, isLoading, mutate };
}
