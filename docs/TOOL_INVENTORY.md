<p align="right">
  <b>English</b> | <a href="./TOOL_INVENTORY_ZH.md">简体中文</a>
</p>

# LLM Tool Inventory

OmniTrade uses a two-layer tool architecture. All tools are managed through MCP servers loaded by **mcp2py** — zero-overhead direct calls, no LLM routing.

## Layer 1: Decision Tool Schemas (4 tools)

These are **schema-only** JSON contracts sent to the LLM. When the LLM calls one, `think_node._parse_decision_from_tool_call()` translates it into a `Decision` entity. No ToolRegistry handlers needed.

Defined in `composition.py._build_tool_schemas()`.

| # | Tool name | Decision action | Notes |
|---|---|---|---|
| 1 | `open_position` | `open` | Includes symbol, side, size, leverage, reason |
| 2 | `close_position` | `close` | Close entire position |
| 3 | `partial_close` | `partial_close` | Close a percentage of position |
| 4 | `hold_tool` | `hold` | No action; last in schema list (counters hold-bias) |

## Layer 2: MCP Tools via mcp2py (15 tools)

All info/crypto tools are MCP servers loaded by `mcp2py.load()`. Tool calls are direct Python function calls through stdio — no LLM routing overhead. Registered in `agents/tools/mcp_tool_bridge.py`.

### omnitrade-trading MCP Server (9 tools)

File: `infrastructure/mcp/trading_mcp_server.py`

| # | Tool name | Description | Dependencies |
|---|---|---|---|
| 1 | `fetch_ticker` | Latest ticker (last/bid/ask/volume) | ExchangeClient (env) |
| 2 | `fetch_ohlcv` | OHLCV candles with timeframe | ExchangeClient (env) |
| 3 | `funding_rate` | Perpetual swap funding rate | ExchangeClient (env) |
| 4 | `order_book` | L2 order book snapshot | ExchangeClient (env) |
| 5 | `open_interest` | Open interest for perp contract | ExchangeClient (env) |
| 6 | `account_snapshot` | Account balance (total/free/uPnL) | ExchangeClient (env) |
| 7 | `list_positions` | Open positions with size/pnl/leverage | ExchangeClient (env) |
| 8 | `open_orders` | Live exchange orders | ExchangeClient (env) |
| 9 | `calculate_risk` | Leverage band + risk budget (pure compute) | — |

### omnitrade-crypto MCP Server (6 tools)

File: `infrastructure/data_sources/crypto_mcp_server.py`

| # | Tool name | Description | Dependencies |
|---|---|---|---|
| 1 | `coingecko_market_overview` | Top coins by market cap | CoinGecko API |
| 2 | `coingecko_trending` | Trending coins (24h) | CoinGecko API |
| 3 | `coingecko_global` | Global market data (mcap, dominance) | CoinGecko API |
| 4 | `fear_greed_index` | Fear & Greed Index (0-100) | Fear & Greed API |
| 5 | `coinglass_derivatives` | Funding rates, OI, long/short ratios | `COINGLASS_API_KEY` |
| 6 | `whale_transactions` | Large on-chain transactions | `WHALE_ALERT_API_KEY` |

## Architecture

```
composition.py
  ├── _build_tool_schemas()     → 4 decision schemas (schema-only)
  └── mcp_tool_bridge.py
        ├── load_mcp_servers()  → mcp2py.load() spawns MCP subprocesses
        └── register_mcp_tools() → ToolRegistry + LLM schemas

LLM → tool_call → think_node
  ├── decision tool → _parse_decision_from_tool_call() → Decision entity
  └── info tool → ToolRegistry.call() → mcp2py direct call → MCP server subprocess
```

## Extensibility

To add a new exchange or asset class:

1. Add MCP tool functions to the appropriate MCP server (or create a new one)
2. Add `mcp2py.load("python -m omnitrade.infrastructure.mcp.new_server")` in `mcp_tool_bridge.py`
3. No changes to `composition.py` or the think loop needed

## Legacy (removed)

The following were replaced by MCP tools:

| Old file | Status |
|---|---|
| `agents/tools/market_data.py` | Replaced by trading MCP server |
| `agents/tools/account_management.py` | Replaced by trading MCP server |
| `agents/tools/risk.py` | Replaced by trading MCP server |
| `agents/tools/external_data.py` | Replaced by crypto MCP server |
| `agents/tools/news_data.py` | Replaced by crypto MCP server |
| `agents/tools/crypto_market_overview.py` | Replaced by crypto MCP server |
| `agents/tools/whale_tracking.py` | Replaced by crypto MCP server |
| `agents/tools/anytool_research.py` | Removed (AnyTool replaced by mcp2py) |
