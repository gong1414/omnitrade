import { apiClient } from "../api/client";

/**
 * Generic SWR fetcher keyed by the API path. Routes paths back into the
 * typed `apiClient` methods to avoid duplicating the URL table.
 */
export async function swrFetcher(key: string): Promise<unknown> {
  if (key === "/api/v1/account") return apiClient.fetchAccount();
  if (key === "/api/v1/positions") return apiClient.fetchPositions();
  if (key === "/api/v1/config") return apiClient.fetchConfig();
  if (key === "/api/v1/rebate") return apiClient.fetchRebate();
  if (key.startsWith("/api/v1/decisions")) {
    const url = new URL(`http://x${key}`);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    return apiClient.fetchDecisions({ limit, offset });
  }
  if (key.startsWith("/api/v1/positions/")) {
    const symbol = decodeURIComponent(key.slice("/api/v1/positions/".length));
    return apiClient.fetchPositionBySymbol(symbol);
  }
  throw new Error(`swrFetcher: unhandled key ${key}`);
}
