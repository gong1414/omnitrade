/**
 * Thin fetch wrapper over Phase 5 REST endpoints.
 *
 * All errors surface as `ApiError` with status + body so SWR can decide
 * whether to retry. Base URL is taken from `NEXT_PUBLIC_API_BASE_URL`
 * (default `http://localhost:8000`).
 */

import type {
  AccountSnapshot,
  ClosePositionRequest,
  ClosePositionResponse,
  ConfigResponse,
  CycleTriggerResponse,
  DecisionsResponse,
  HealthResponse,
  HistoryResponse,
  HistoryWindow,
  Position,
  PositionsResponse,
  RebateSummary,
  RunApprovalResponse,
  StatsResponse,
  StrategyResponse,
  TradesResponse,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

function resolveBaseUrl(explicit?: string): string {
  if (explicit) return explicit.replace(/\/$/, "");
  const envUrl =
    typeof process !== "undefined" ? process.env.NEXT_PUBLIC_API_BASE_URL : undefined;
  // Default to a relative URL so requests ride the Next same-origin
  // rewrite proxy declared in `next.config.mjs`. Set
  // `NEXT_PUBLIC_API_BASE_URL` only when serving the bundle from a
  // different origin than the backend.
  return (envUrl ?? "").replace(/\/$/, "");
}

async function request<T>(
  path: string,
  init: RequestInit,
  opts: ApiClientOptions,
): Promise<T> {
  const baseUrl = resolveBaseUrl(opts.baseUrl);
  const doFetch = opts.fetchImpl ?? fetch;
  const res = await doFetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const detail =
      body && typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, body, detail);
  }
  return body as T;
}

export function createApiClient(options: ApiClientOptions = {}) {
  const opts = options;
  return {
    getHealth: () => request<HealthResponse>(`/api/health`, { method: "GET" }, opts),

    fetchAccount: () =>
      request<AccountSnapshot>(`/api/v1/account`, { method: "GET" }, opts),

    fetchPositions: () =>
      request<PositionsResponse>(`/api/v1/positions`, { method: "GET" }, opts),

    fetchPositionBySymbol: (symbol: string) =>
      request<Position>(
        `/api/v1/positions/${encodeURIComponent(symbol)}`,
        { method: "GET" },
        opts,
      ),

    fetchDecisions: ({
      limit = 50,
      offset = 0,
      include,
    }: { limit?: number; offset?: number; include?: string } = {}) => {
      const search = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      if (include) search.set("include", include);
      return request<DecisionsResponse>(
        `/api/v1/decisions?${search.toString()}`,
        { method: "GET" },
        opts,
      );
    },

    fetchConfig: () => request<ConfigResponse>(`/api/v1/config`, { method: "GET" }, opts),

    fetchRebate: () => request<RebateSummary>(`/api/v1/rebate`, { method: "GET" }, opts),

    fetchHistory: (window: HistoryWindow = "24h") =>
      request<HistoryResponse>(
        `/api/history?window=${window}`,
        { method: "GET" },
        opts,
      ),

    fetchStats: () => request<StatsResponse>(`/api/stats`, { method: "GET" }, opts),

    fetchStrategy: () =>
      request<StrategyResponse>(`/api/strategy`, { method: "GET" }, opts),

    fetchTrades: ({ limit = 50, offset = 0 }: { limit?: number; offset?: number } = {}) =>
      request<TradesResponse>(
        `/api/v1/trades?limit=${limit}&offset=${offset}`,
        { method: "GET" },
        opts,
      ),

    closePosition: (body: ClosePositionRequest) =>
      request<ClosePositionResponse>(
        `/api/v1/actions/close-position`,
        { method: "POST", body: JSON.stringify(body) },
        opts,
      ),

    triggerCycle: () =>
      request<CycleTriggerResponse>(
        `/api/v1/cycle/trigger`,
        { method: "POST" },
        opts,
      ),

    // T9 — HITL approvals on large opens. Resolves the asyncio.Future
    // the trading agent registered when the open exceeded
    // ``HITL_OPEN_SIZE_THRESHOLD_USD``. The 404 path (no pending
    // approval) is the operator-double-click case; consumers should
    // swallow it.
    confirmRun: (runId: string) =>
      request<RunApprovalResponse>(
        `/api/v1/runs/${encodeURIComponent(runId)}/confirm`,
        { method: "POST" },
        opts,
      ),

    rejectRun: (runId: string) =>
      request<RunApprovalResponse>(
        `/api/v1/runs/${encodeURIComponent(runId)}/reject`,
        { method: "POST" },
        opts,
      ),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Default client — reads env at call time, safe for both SSR and CSR. */
export const apiClient: ApiClient = createApiClient();
