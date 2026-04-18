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
    { refreshInterval: 5000, revalidateOnFocus: false },
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
