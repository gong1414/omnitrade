/**
 * TypeScript types matching Phase 5 backend Pydantic response models verbatim.
 *
 * IMPORTANT: These types are hand-synced to the backend route handlers in
 * `apps/backend/src/omnitrade/api/routes/`. All numeric fields are serialised
 * as strings by the backend (Decimal → str) to preserve precision.
 *
 * Source of truth (per-endpoint):
 *   - `/health`                          → api/main.py
 *   - `/api/v1/account`                  → api/routes/account.py + application/account_service.py
 *   - `/api/v1/positions`                → api/routes/positions.py
 *   - `/api/v1/positions/{symbol}`       → api/routes/positions.py
 *   - `/api/v1/decisions`                → api/routes/decisions.py
 *   - `/api/v1/config`                   → api/routes/config.py
 *   - `/api/v1/actions/close-position`   → api/routes/actions.py
 *   - `/api/v1/rebate`                   → api/routes/rebate.py
 *   - `/ws/stream`                       → api/ws/stream.py + application/events/bus.py
 */

// ── /health ───────────────────────────────────────────────────────────────

export interface HealthResponse {
  ok: boolean;
  time: string;
  environment: string;
  version: string;
}

// ── /api/v1/account ───────────────────────────────────────────────────────

export interface AccountSnapshot {
  timestamp: string;
  total_value: string;
  available_cash: string;
  unrealized_pnl: string;
  realized_pnl: string;
  return_percent: string;
  sharpe_ratio: string | null;
  peak: string;
  drawdown_percent: string;
}

// ── /api/v1/positions ─────────────────────────────────────────────────────

export interface Position {
  id: number;
  symbol: string;
  side: "long" | "short" | string;
  quantity: string;
  entry_price: string;
  current_price: string;
  leverage: number;
  unrealized_pnl: string;
  stop_loss: string | null;
  trailing_peak_pnl_pct: string;
  cumulative_close_pct: string;
  opened_at: string;
  confidence: string | null;
}

export interface PositionsResponse {
  positions: Position[];
  count: number;
}

// ── /api/v1/decisions ─────────────────────────────────────────────────────

export interface AgentDecisionPlan {
  entry?: number | null;
  stop_loss?: number | null;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  risk_usd?: number | null;
  r_multiple_target?: number | null;
}

export interface AgentDecision {
  id: number;
  timestamp: string;
  iteration: number;
  decision: string;
  market_analysis: string;
  actions_taken: string;
  account_value: string;
  positions_count: number;
  correlation_id: string | null;
  // Structured reasoning fields (PR-B2 — null until backend writes them)
  market_context?: string | null;
  gates_passed?: string[] | null;
  invalidation_condition?: string | null;
  plan?: AgentDecisionPlan | null;
  structured_confidence?: number | null;
  output_language?: "zh" | "en" | null;
}

export interface DecisionsResponse {
  decisions: AgentDecision[];
  count: number;
  limit: number;
  offset: number;
}

// ── /api/v1/config ────────────────────────────────────────────────────────

export interface ConfigResponse {
  trading_strategy: string | null;
  trading_interval_minutes: number | null;
  max_leverage: number | null;
  max_positions: number | null;
  max_holding_hours: number | null;
  extreme_stop_loss_percent: string | null;
  initial_balance_usdt: string | null;
  account_stop_loss_usdt: string | null;
  account_take_profit_usdt: string | null;
  account_record_interval_minutes: number | null;
  account_drawdown_warning_percent: string | null;
  account_drawdown_no_new_position_percent: string | null;
  account_drawdown_force_close_percent: string | null;
  exchange: string | null;
  gate_use_testnet: boolean | null;
  okx_use_testnet: boolean | null;
  llm_provider: string | null;
  llm_model_name: string | null;
  fee_rebate_percent: string | null;
  environment: string | null;
  log_level: string | null;
  exchange_fee_rate: string | null;
}

// ── /api/v1/actions/close-position ────────────────────────────────────────

export interface ClosePositionRequest {
  symbol: string;
  password: string;
  /** Optional audit reason. Defaults to "manual" server-side. */
  reason?: string;
  /**
   * NOTE: Phase 5 backend does not accept `percentage` — it fully closes the
   * position. The field is reserved for a Phase 7 partial-close extension.
   */
  percentage?: number;
}

export interface ClosePositionResponse {
  order_id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  fee: string | null;
  status: string;
}

// ── /api/v1/rebate ────────────────────────────────────────────────────────

export interface RebateSummary {
  window_start: string;
  window_end: string;
  fee_rebate_percent: string;
  close_trades_count: number;
  total_fees_usdt: string;
  rebate_amount_usdt: string;
}

// ── /ws/stream ────────────────────────────────────────────────────────────

export type WsEventType =
  | "position_update"
  | "decision_update"
  | "account_update"
  | "orchestrator_error";

export interface WsEnvelope<T = unknown> {
  type: WsEventType;
  payload: T;
  trace_id: string;
  ts: string;
}

export type AccountUpdatePayload = AccountSnapshot;
export type PositionUpdatePayload = Position;
export type DecisionUpdatePayload = AgentDecision;

// Phase 8.5a (plan v3 G-5): multi-agent orchestrator degradation envelope.
export interface OrchestratorErrorPayload {
  strategy: string;
  correlation_id: string;
  reason: string;
}
