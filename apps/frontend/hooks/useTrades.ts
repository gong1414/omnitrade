"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { TradesResponse } from "@/lib/api/types";

export const TRADES_KEY = "/api/v1/trades";

export function useTrades(limit = 50, offset = 0) {
  const { data, error, isLoading, mutate } = useSWR<TradesResponse>(
    `${TRADES_KEY}?limit=${limit}&offset=${offset}`,
    () => apiClient.fetchTrades({ limit, offset }),
    { refreshInterval: 10000, revalidateOnFocus: false },
  );
  return {
    trades: data?.trades ?? [],
    total: data?.total ?? 0,
    limit: data?.limit ?? limit,
    offset: data?.offset ?? offset,
    error,
    isLoading,
    mutate,
  };
}
