"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { DecisionsResponse } from "@/lib/api/types";

export function decisionsKey(limit = 50, offset = 0) {
  return `/api/v1/decisions?limit=${limit}&offset=${offset}`;
}

export function useDecisions({ limit = 50, offset = 0 }: { limit?: number; offset?: number } = {}) {
  const key = decisionsKey(limit, offset);
  const { data, error, isLoading, mutate } = useSWR<DecisionsResponse>(
    key,
    () => apiClient.fetchDecisions({ limit, offset }),
    // SSE `decision_update` triggers a global mutate of every
    // `/api/v1/decisions...` key, so the periodic poll is redundant.
    { revalidateOnFocus: false },
  );
  return {
    decisions: data?.decisions ?? [],
    count: data?.count ?? 0,
    error,
    isLoading,
    mutate,
    key,
  };
}
