<p align="right">
  <b>English</b> | <a href="./TOOL_INVENTORY_ZH.md">简体中文</a>
</p>

# LLM Tool Inventory

OmniTrade uses a two-layer tool architecture. The trading agent is an
[Agno](https://github.com/agno-agi/agno) `Agent`; tools are split between
**DecisionRecorder schemas** (the four tool calls that yield the final
`Decision`) and the **MultiMCPTools toolkit** (read-only market / crypto
context tools loaded from FastMCP stdio servers).

## Layer 1: Decision Recorder Tools (4 tools)

Defined in `agents/tools/decision_schemas.py`. Each tool is a pure
recorder: when the LLM picks one, Agno fires the corresponding async
function which writes the LLM's intent into a per-cycle
`DecisionRecorder` and returns a small acknowledgement payload. Real
trade execution happens later in `composition._build_execute_fn`.

| # | Tool name | Decision action | Notes |
|---|---|---|---|
| 1 | `open_position` | `open` | Includes symbol, side, size, leverage, structured reason |
| 2 | `close_position` | `close` | Close entire position |
| 3 | `partial_close` | `partial_close` | Close a percentage of position |
| 4 | `hold_tool` | `hold` | No action; last in schema list (counters hold-bias) |

When `agent.arun(...)` returns, the recorder either holds a `Decision`
or `None` — the `None` case resolves to `Decision(action="hold", ...)`
so a misbehaving cycle still produces a row.

## Layer 2: MCP Tools via Agno MultiMCPTools (15 tools)

The Agno `MultiMCPTools` bridge in `agents/tools/mcp_bridge.py` spawns
two FastMCP stdio subprocesses and discovers their tools automatically.
Tool calls are direct Python functions invoked over stdio — no extra
LLM routing.

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
agents/trading_agent.py::build_agno_think_fn
  ├── DecisionRecorder + build_decision_tools  → 4 decision recorders
  └── AgnoMCPBridge.connect()                  → MultiMCPTools toolkit
        spawns:
          ├─ python -m omnitrade.infrastructure.mcp.trading_mcp_server
          └─ python -m omnitrade.infrastructure.data_sources.crypto_mcp_server

per-cycle:
  Agent(model=DeepSeek(...), tools=[mcp_toolkit, *decision_recorders]).arun(prompt)
    ├── decision tool call → DecisionRecorder captures Decision
    └── info tool call     → MCP stdio → server subprocess → response
```

## Extensibility

To add a new exchange or asset class:

1. Add MCP tool functions to the appropriate FastMCP server (or add a
   new `python -m ...` entrypoint under `infrastructure/`).
2. Add the new entrypoint to `_DEFAULT_COMMANDS` in
   `agents/tools/mcp_bridge.py`.
3. No changes to the Agno Agent or trading loop are needed — the new
   tools are auto-discovered on next bridge connect.
