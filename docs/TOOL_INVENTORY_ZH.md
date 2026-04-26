<p align="right">
  <a href="./TOOL_INVENTORY.md">English</a> | <b>简体中文</b>
</p>

# LLM 工具清单

OmniTrade 采用两层工具架构。交易代理是 [Agno](https://github.com/agno-agi/agno)
的 `Agent`；工具分为两层：**DecisionRecorder schema**（四个产出最终
`Decision` 的工具调用）和 **MultiMCPTools 工具集**（从 FastMCP stdio
服务器加载的只读行情 / 加密上下文工具）。

## 第一层：决策记录工具（4 个）

定义在 `agents/tools/decision_schemas.py`。每个工具都是 *纯记录器*：
当 LLM 调用其中一个时，Agno 触发对应的 async 函数，把 LLM 的意图写入
本轮的 `DecisionRecorder`，并返回一个小的确认 payload。真正的下单仍
在后续 `composition._build_execute_fn` 中执行。

| # | 工具名 | 决策动作 | 说明 |
|---|---|---|---|
| 1 | `open_position` | `open` | 含 symbol、side、size、leverage、structured reason |
| 2 | `close_position` | `close` | 全部平仓 |
| 3 | `partial_close` | `partial_close` | 按比例部分平仓 |
| 4 | `hold_tool` | `hold` | 不操作；在 schema 列表中排最后（对抗 hold 偏好） |

`agent.arun(...)` 返回后，recorder 要么持有 `Decision`，要么为 `None`
—— `None` 时回退为 `Decision(action="hold", ...)`，让错乱的周期也能落
盘一行。

## 第二层：通过 Agno MultiMCPTools 提供的 MCP 工具（15 个）

`agents/tools/mcp_bridge.py` 中的 Agno `MultiMCPTools` 桥接器会启动两
个 FastMCP stdio 子进程，并自动发现它们的工具。工具调用是通过 stdio
执行的 Python 直调 —— 没有额外的 LLM 路由开销。

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
agents/trading_agent.py::build_agno_think_fn
  ├── DecisionRecorder + build_decision_tools  → 4 个决策记录器
  └── AgnoMCPBridge.connect()                  → MultiMCPTools 工具集
        启动子进程：
          ├─ python -m omnitrade.infrastructure.mcp.trading_mcp_server
          └─ python -m omnitrade.infrastructure.data_sources.crypto_mcp_server

每轮：
  Agent(model=DeepSeek(...), tools=[mcp_toolkit, *decision_recorders]).arun(prompt)
    ├── 决策工具调用 → DecisionRecorder 捕获 Decision
    └── 信息工具调用 → MCP stdio → 服务器子进程 → 响应
```

## 可扩展性

添加新交易所或资产类别：

1. 在对应 FastMCP 服务器中添加工具函数（或在 `infrastructure/` 下创
   建新的 `python -m ...` 入口）。
2. 把新入口加入 `agents/tools/mcp_bridge.py` 的 `_DEFAULT_COMMANDS`。
3. 不需要修改 Agno Agent 或交易循环 —— 下次 bridge connect 时新工具
   会被自动发现。
