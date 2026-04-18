"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api/client";
import type { AccountSnapshot } from "@/lib/api/types";

export const ACCOUNT_KEY = "/api/v1/account";

export function useAccount() {
  const { data, error, isLoading, mutate } = useSWR<AccountSnapshot>(
    ACCOUNT_KEY,
    () => apiClient.fetchAccount(),
    { refreshInterval: 5000, revalidateOnFocus: false },
  );
  return { account: data, error, isLoading, mutate };
}
