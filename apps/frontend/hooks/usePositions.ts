"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { PositionsResponse } from "@/lib/api/types";

export const POSITIONS_KEY = "/api/v1/positions";

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR<PositionsResponse>(
    POSITIONS_KEY,
    () => apiClient.fetchPositions(),
    { refreshInterval: 5000, revalidateOnFocus: false },
  );
  return { positions: data?.positions ?? [], count: data?.count ?? 0, error, isLoading, mutate };
}
