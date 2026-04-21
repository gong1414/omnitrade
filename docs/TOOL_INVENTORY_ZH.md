<p align="right">
  <a href="./TOOL_INVENTORY.md">English</a> | <b>简体中文</b>
</p>

# LLM 工具清单

OmniTrade 采用两层工具架构。所有工具通过 **mcp2py** 加载的 MCP 服务器管理 —— 直接函数调用，零开销，无 LLM 路由。

## 第一层：决策工具 Schema（4 个工具）

这些是**纯 schema** 的 JSON 契约，发送给 LLM。LLM 调用时，`think_node._parse_decision_from_tool_call()` 将其转换为 `Decision` 实体。不需要 ToolRegistry 处理器。

定义在 `composition.py._build_tool_schemas()`。

| # | 工具名 | 决策动作 | 说明 |
|---|---|---|---|
| 1 | `open_position` | `open` | 含 symbol、side、size、leverage、reason |
| 2 | `close_position` | `close` | 全部平仓 |
| 3 | `partial_close` | `partial_close` | 按比例部分平仓 |
| 4 | `hold_tool` | `hold` | 不操作；在 schema 列表中排最后（对抗 hold 偏好） |

## 第二层：MCP 工具（mcp2py 直调，15 个工具）

所有行情/加密工具由 `mcp2py.load()` 加载的 MCP 服务器提供。工具调用是通过 stdio 的直接 Python 函数调用 —— 无 LLM 路由开销。注册在 `agents/tools/mcp_tool_bridge.py`。

### omnitrade-trading MCP 服务器（9 个工具）

文件：`infrastructure/mcp/trading_mcp_server.py`

| # | 工具名 | 说明 | 依赖 |
|---|---|---|---|
| 1 | `fetch_ticker` | 最新行情（最新价/买/卖/成交量） | ExchangeClient（环境变量） |
| 2 | `fetch_ohlcv` | K 线数据（含时间周期） | ExchangeClient（环境变量） |
| 3 | `funding_rate` | 永续合约资金费率 | ExchangeClient（环境变量） |
| 4 | `order_book` | L2 盘口快照 | ExchangeClient（环境变量） |
| 5 | `open_interest` | 持仓量 | ExchangeClient（环境变量） |
| 6 | `account_snapshot` | 账户余额（总额/可用/未实现盈亏） | ExchangeClient（环境变量） |
| 7 | `list_positions` | 当前持仓（数量/盈亏/杠杆） | ExchangeClient（环境变量） |
| 8 | `open_orders` | 活跃委托 | ExchangeClient（环境变量） |
| 9 | `calculate_risk` | 杠杆区间 + 风险预算（纯计算） | — |

### omnitrade-crypto MCP 服务器（6 个工具）

文件：`infrastructure/data_sources/crypto_mcp_server.py`

| # | 工具名 | 说明 | 依赖 |
|---|---|---|---|
| 1 | `coingecko_market_overview` | 按市值排名的币种数据 | CoinGecko API |
| 2 | `coingecko_trending` | 热门币种（24h） | CoinGecko API |
| 3 | `coingecko_global` | 全球市场数据（总市值、BTC 占比） | CoinGecko API |
| 4 | `fear_greed_index` | 恐惧与贪婪指数（0-100） | Fear & Greed API |
| 5 | `coinglass_derivatives` | 资金费率、持仓量、多空比 | `COINGLASS_API_KEY` |
| 6 | `whale_transactions` | 大额链上转账追踪 | `WHALE_ALERT_API_KEY` |

## 架构

```
composition.py
  ├── _build_tool_schemas()     → 4 个决策 schema（纯 schema）
  └── mcp_tool_bridge.py
        ├── load_mcp_servers()  → mcp2py.load() 启动 MCP 子进程
        └── register_mcp_tools() → ToolRegistry + LLM schema

LLM → tool_call → think_node
  ├── 决策工具 → _parse_decision_from_tool_call() → Decision 实体
  └── 信息工具 → ToolRegistry.call() → mcp2py 直调 → MCP 服务器子进程
```

## 可扩展性

添加新交易所或资产类别：

1. 在对应 MCP 服务器中添加工具函数（或创建新 MCP 服务器）
2. 在 `mcp_tool_bridge.py` 中添加 `mcp2py.load("python -m omnitrade.infrastructure.mcp.new_server")`
3. 无需修改 `composition.py` 或 think loop

## 已移除的遗留文件

以下文件已被 MCP 工具替代：

| 旧文件 | 状态 |
|---|---|
| `agents/tools/market_data.py` | 替代为 trading MCP 服务器 |
| `agents/tools/account_management.py` | 替代为 trading MCP 服务器 |
| `agents/tools/risk.py` | 替代为 trading MCP 服务器 |
| `agents/tools/external_data.py` | 替代为 crypto MCP 服务器 |
| `agents/tools/news_data.py` | 替代为 crypto MCP 服务器 |
| `agents/tools/crypto_market_overview.py` | 替代为 crypto MCP 服务器 |
| `agents/tools/whale_tracking.py` | 替代为 crypto MCP 服务器 |
| `agents/tools/anytool_research.py` | 已移除（AnyTool 被 mcp2py 替代） |
