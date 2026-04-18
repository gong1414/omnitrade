<p align="right">
  <b>English</b> | <a href="./TOOL_INVENTORY_ZH.md">简体中文</a>
</p>

# LLM Tool Inventory

Matrix of agent-exposed LLM tools and their Python handlers.

| # | Tool name | Python handler | ExchangeClient method | Phase |
|---|---|---|---|---|
| 1 | `getMarketPriceTool` | `build_fetch_ticker_tool` | `fetch_ticker` | 4.x |
| 2 | `getTechnicalIndicatorsTool` | `build_fetch_ohlcv_tool` (+ indicators via 8.2) | `fetch_ohlcv` | 4.x / 8.2 |
| 3 | `getFundingRateTool` | `build_funding_rate_tool` | `fetch_funding_rate` | **8.4** |
| 4 | `getOrderBookTool` | `build_order_book_tool` | `fetch_order_book` | **8.4** |
| 5 | `getOpenInterestTool` | `build_open_interest_tool` | `fetch_open_interest` | **8.4** |
| 6 | `getAccountBalanceTool` | `build_account_snapshot_tool` | `fetch_balance` | 4.x |
| 7 | `getPositionsTool` | `build_list_positions_tool` | `fetch_positions` | 4.x |
| 8 | `getOpenOrdersTool` | `build_open_orders_tool` | `fetch_open_orders` | **8.4** |
| 9 | `checkOrderStatusTool` | `build_check_order_status_tool` | `fetch_order` | **8.4** |
| 10 | `calculateRiskTool` | `build_calculate_risk_tool` | — (domain service) | **8.4** |
| 11 | `syncPositionsTool` | `build_sync_positions_tool` (read-only diff) | `fetch_positions` + `PositionRepository.list_all` | **8.4** |
| 12 | `getCryptoNewsTool` | `build_news_data_tool` | — (NewsFetcher) | 4.x |
| 13 | `getExchangeAnnouncementsTool` | `build_external_data_tool` (external fetcher) | — (ExternalFetcher) | 4.x |
| 14 | `getLatestEventsTool` | `build_external_data_tool` (same fetcher, different endpoint) | — | 4.x |
| 15 | `openPositionTool` | `build_open_position_tool` | `place_order` | 4.x |
| 16 | `closePositionTool` | `build_close_position_tool` (+ partial) | `close_position` | 4.x |
| 17 | `cancelOrderTool` | `build_cancel_order_tool` | `cancel_order` | **8.4** |

## Notes

**Naming convention**: Tool names over the LLM boundary use `camelCase`
(e.g. `fundingRate`, `orderBook`, `cancelOrder`) so cassette replay
stays byte-exact on `tool_calls[].function.name`. Internal Python
builders keep `snake_case` (`fetch_ticker`, etc.).

**`syncPositions` is READ-ONLY when invoked by the LLM.** The tool
returns a diff dict (symbols only-on-exchange, only-in-local, size
mismatches); it never writes. Actual reconciliation lives in
`scripts/sync_positions.py` (Phase 8.6) behind `--apply --yes-really`.

**Ordering inside the plan.** Phase 8.4 only adds tool builders +
ExchangeClient implementations; tool *registration* into
`ToolRegistry` (and thus visibility to the main LLM) lands in Phase
8.5a alongside the multi-agent orchestrator roster work, because
registering them now would leak new capabilities before the
`tool_choice="required"` transition (Phase 8.5b) is in place.

**Rollback pair.** Phase 8.4 depends on Phase 8.0 port-boundary stubs.
Reverting 8.4 in isolation restores `NotImplementedError` stubs; set
`settings.degraded_exchange_methods_ok=true` if you need to silently
downgrade tool calls to no-ops during a partial rollback.

## Phase 8.6 pre-work — ccxt.pro LICENSE spike (MINOR-6)

- **Spike date:** 2026-04-18 (Phase 8.6 executor kickoff).
- **Finding:** `ccxt.pro` (legacy standalone package) and its merged
  successor (`ccxt` ≥ 4.0 with WebSocket support) are both distributed
  under the MIT License (see upstream `ccxt/ccxt` repo `LICENSE.txt`;
  PyPI metadata for `ccxt` lists `License: MIT`). MIT is compatible
  with this project's license (also MIT).
- **Decision:** F2 (hand-rolled `websockets>=12` against `okx_ws.py` +
  `gate_ws.py` siblings) remains the chosen ADR-F path for Phase 8.6
  — scope isolation, deterministic cycle contract, and minimal
  dependency surface outweigh the license question.
- **Follow-up (open):** Future phases may reconsider F1 (ccxt.pro / ccxt
  WS) now that the license is confirmed MIT-compatible. Re-evaluate
  after 48 h staging soak of the hand-rolled path.
