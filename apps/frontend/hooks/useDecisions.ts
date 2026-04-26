"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { DecisionsResponse } from "@/lib/api/types";

export function decisionsKey(limit = 50, offset = 0, include?: string) {
  const base = `/api/v1/decisions?limit=${limit}&offset=${offset}`;
  return include ? `${base}&include=${include}` : base;
}

export function useDecisions({
  limit = 50,
  offset = 0,
  include,
}: { limit?: number; offset?: number; include?: string } = {}) {
  const key = decisionsKey(limit, offset, include);
  const { data, error, isLoading, mutate } = useSWR<DecisionsResponse>(
    key,
    () => apiClient.fetchDecisions({ limit, offset, include }),
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
