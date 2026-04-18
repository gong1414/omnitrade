<p align="right">
  <a href="./TOOL_INVENTORY.md">English</a> | <b>简体中文</b>
</p>

# LLM 工具清单

Agent 对 LLM 暴露的工具与 Python 处理器的对照矩阵。

| # | 工具名 | Python 构造器 | ExchangeClient 方法 | 阶段 |
|---|---|---|---|---|
| 1 | `getMarketPriceTool` | `build_fetch_ticker_tool` | `fetch_ticker` | 4.x |
| 2 | `getTechnicalIndicatorsTool` | `build_fetch_ohlcv_tool`（+ 8.2 引入 indicator） | `fetch_ohlcv` | 4.x / 8.2 |
| 3 | `getFundingRateTool` | `build_funding_rate_tool` | `fetch_funding_rate` | **8.4** |
| 4 | `getOrderBookTool` | `build_order_book_tool` | `fetch_order_book` | **8.4** |
| 5 | `getOpenInterestTool` | `build_open_interest_tool` | `fetch_open_interest` | **8.4** |
| 6 | `getAccountBalanceTool` | `build_account_snapshot_tool` | `fetch_balance` | 4.x |
| 7 | `getPositionsTool` | `build_list_positions_tool` | `fetch_positions` | 4.x |
| 8 | `getOpenOrdersTool` | `build_open_orders_tool` | `fetch_open_orders` | **8.4** |
| 9 | `checkOrderStatusTool` | `build_check_order_status_tool` | `fetch_order` | **8.4** |
| 10 | `calculateRiskTool` | `build_calculate_risk_tool` | — （domain 服务） | **8.4** |
| 11 | `syncPositionsTool` | `build_sync_positions_tool`（只读 diff） | `fetch_positions` + `PositionRepository.list_all` | **8.4** |
| 12 | `getCryptoNewsTool` | `build_news_data_tool` | — （NewsFetcher） | 4.x |
| 13 | `getExchangeAnnouncementsTool` | `build_external_data_tool`（外部抓取器） | — （ExternalFetcher） | 4.x |
| 14 | `getLatestEventsTool` | `build_external_data_tool`（同 fetcher，不同端点） | — | 4.x |
| 15 | `openPositionTool` | `build_open_position_tool` | `place_order` | 4.x |
| 16 | `closePositionTool` | `build_close_position_tool`（+ 部分平仓） | `close_position` | 4.x |
| 17 | `cancelOrderTool` | `build_cancel_order_tool` | `cancel_order` | **8.4** |

## 说明

**命名约定**：LLM 边界上的工具名用 `camelCase`（如 `fundingRate`、`orderBook`、`cancelOrder`），这样 cassette 重放在 `tool_calls[].function.name` 上 byte-exact。Python 内部构造器保留 `snake_case`（`fetch_ticker` 等）。

**`syncPositions` 被 LLM 调用时只读。** 工具返回一个 diff 字典（仅交易所有 / 仅本地有 / size 不一致的 symbol），不写。真正的协调在 `scripts/sync_positions.py`（阶段 8.6），藏在 `--apply --yes-really` 后。

**阶段内顺序。** 阶段 8.4 只加工具构造器 + ExchangeClient 实现；工具**注册**进 `ToolRegistry`（即对主 LLM 可见）要到阶段 8.5a、配合多智能体编排的名册工作一起落地；否则会在 `tool_choice="required"` 迁移（阶段 8.5b）之前就泄漏新能力。

**回滚对。** 阶段 8.4 依赖 8.0 端口桩。单独回滚 8.4 就是回到 `NotImplementedError` 桩；如果需要在部分回滚期间把工具调用静默降级成 no-op，设 `settings.degraded_exchange_methods_ok=true`。

## 阶段 8.6 预研 —— ccxt.pro LICENSE spike（MINOR-6）

- **Spike 日期：** 2026-04-18（阶段 8.6 executor kickoff）。
- **结论：** `ccxt.pro`（legacy 独立包）及其合并后的继任者（`ccxt` ≥ 4.0，带 WebSocket 支持）都以 MIT License 发布（见上游 `ccxt/ccxt` 仓 `LICENSE.txt`；`ccxt` 的 PyPI metadata 里 `License: MIT`）。MIT 与本项目同一许可证，兼容。
- **决策：** F2（手写 `websockets>=12` + `okx_ws.py` + `gate_ws.py` 同级）仍然是阶段 8.6 ADR-F 选择的路径 —— 作用域隔离、确定性周期契约、最小依赖面，优先级高于 license 问题。
- **Follow-up（开放）：** 未来阶段可重新评估 F1（ccxt.pro / ccxt WS），license 已确认 MIT 兼容。手写路径在 staging 跑满 48h 后再评估。
