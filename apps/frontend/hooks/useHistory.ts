"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { HistoryResponse, HistoryWindow } from "@/lib/api/types";

export function historyKey(window: HistoryWindow) {
  return `/api/history?window=${window}`;
}

export function useHistory(window: HistoryWindow = "24h") {
  const { data, error, isLoading, mutate } = useSWR<HistoryResponse>(
    historyKey(window),
    () => apiClient.fetchHistory(window),
    { refreshInterval: 30_000, revalidateOnFocus: false },
  );
  return { history: data, error, isLoading, mutate };
}
