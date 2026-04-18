<p align="center">
  <b>English</b> | <a href="README_ZH.md">简体中文</a>
</p>


<h1 align="center">OmniTrade: LLM-Driven Crypto Futures Arena</h1>

<p align="center">
  <b>11 competing strategies · 4 close-path taxonomy · atomic three-way state · real-time dashboard</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-Next.js%2014-000000?style=flat&logo=next.js&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/LLM-LiteLLM-8A2BE2?style=flat" alt="LiteLLM">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat" alt="License"></a>
  <br>
  <img src="https://img.shields.io/badge/Strategies-11-FF6B6B" alt="Strategies">
  <img src="https://img.shields.io/badge/Close_Paths-4%2B1-4ECDC4" alt="Close Paths">
  <img src="https://img.shields.io/badge/Frozen_Fixtures-22%2F22-FFD93D" alt="Fixtures">
  <img src="https://img.shields.io/badge/Tests-642_green-2BB673" alt="Tests">
  <img src="https://img.shields.io/badge/Exchanges-Gate%20%2B%20OKX-F6465D" alt="Exchanges">
</p>

<p align="center">
  <a href="#-key-features">Features</a> &nbsp;&middot;&nbsp;
  <a href="#-what-is-omnitrade">What Is It</a> &nbsp;&middot;&nbsp;
  <a href="#-strategies">Strategies</a> &nbsp;&middot;&nbsp;
  <a href="#-get-started">Get Started</a> &nbsp;&middot;&nbsp;
  <a href="#-architecture">Architecture</a> &nbsp;&middot;&nbsp;
  <a href="#-environment">Env</a> &nbsp;&middot;&nbsp;
  <a href="#-api-reference">API</a> &nbsp;&middot;&nbsp;
  <a href="#-roadmap">Roadmap</a> &nbsp;&middot;&nbsp;
  <a href="#-license">License</a>
</p>

---

## 💡 What Is OmniTrade?

OmniTrade is an autonomous **crypto-futures trading arena** where 11 LLM-driven strategies compete for PnL on Gate.io or OKX perpetuals. Point it at a testnet, pick a strategy, and watch the agent reason about markets, size positions, and manage risk — with every decision verifiable via a 22-fixture characterization gate.

### Key Capabilities

- **11 named strategies** — from `arena-guardian` (capital-preservation) through `arena-raider-squad` (multi-agent attack team) to `arena-autopilot` (fully autonomous LLM)
- **4-path close-path taxonomy** — `stop_loss`, `trailing_stop`, `partial_profit`, `ai_decision`, plus `none`; enforced by a pure classifier and three 10-second monitors
- **Atomic three-way state contract** — `cumulative_close_pct`, `stop_loss`, `trailing_peak_pnl_pct` land in a single SQL `UPDATE` so the stop-loss monitor can never read a torn write
- **Testnet by default** — `GATE_USE_TESTNET=true` / `OKX_USE_TESTNET=true` out of the box; live trading requires explicit override
- **Characterization gate** — 22 frozen fixtures replay deterministically at ≥ 0.95 Decision-equivalent pass rate
- **Real-time dashboard** — Next.js 14 App Router + SWR + WebSocket with exponential-backoff reconnect

---

## ✨ Key Features

<table width="100%">
  <tr>
    <td align="center" width="25%" valign="top">
      <h3>🎯 Strategy Arena</h3>
      <img src="https://img.shields.io/badge/11_Strategies-FF6B6B?style=for-the-badge" alt="Strategies"/><br><br>
      <div align="left">
        • 11 named strategies across 3 risk profiles<br>
        • 2 prompt branches: minimal (autopilot / dual-signal) vs full "World-class Trader"<br>
        • Per-strategy leverage bands, trailing ladder, partial-profit stages<br>
        • Multi-agent modes: <code>arena-tribunal</code> (3-expert jury) &amp; <code>arena-raider-squad</code> (4-expert team)
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🛡️ Close-Path Classifier</h3>
      <img src="https://img.shields.io/badge/4%2B1_Buckets-4ECDC4?style=for-the-badge" alt="Buckets"/><br><br>
      <div align="left">
        • Pure classifier: <code>close_path_classifier.py</code><br>
        • 10-s monitors: trailing-stop, stop-loss, partial-profit<br>
        • AI closes via <code>close_position</code> / <code>partial_close</code> tools<br>
        • Three-way state written atomically on every close
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🔌 Exchange Client</h3>
      <img src="https://img.shields.io/badge/Gate%20%2B%20OKX-FFD93D?style=for-the-badge" alt="Exchange"/><br><br>
      <div align="left">
        • ccxt unified adapter; testnet default<br>
        • REST: ticker, OHLCV, order book, open interest, funding<br>
        • WebSocket market stream (hand-rolled <code>websockets&gt;=12</code>)<br>
        • Order lifecycle: open, close, partial close, cancel
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🧪 Characterization Gate</h3>
      <img src="https://img.shields.io/badge/22%2F22_Frozen-C77DFF?style=for-the-badge" alt="Gate"/><br><br>
      <div align="left">
        • 22 hand-curated decision contracts<br>
        • VCR cassettes synthesised deterministically<br>
        • Decision-equivalent replay ≥ 0.95 pass-rate<br>
        • Every close-path bucket ≥ 0.95, drift ≤ 0.05
      </div>
    </td>
  </tr>
</table>

---

## 🎯 Strategies

11 strategies, each a concrete configuration of **leverage band → trailing ladder → partial-profit stages → stop-loss override → system-prompt branch**.

| # | Enum value | Profile | Prompt branch | Code-level protection | Frozen fixtures |
|---|---|---|---|---|---|
| 1 | `arena-guardian` | capital-preservation | full | off | `case_06`, `case_19` |
| 2 | `arena-steward` | balanced default | full | off | `case_05`, `case_11`, `case_18` |
| 3 | `arena-raider` | high-leverage single-agent | full | off | `case_07` |
| 4 | `arena-raider-squad` | multi-agent attack team (4 experts) | team | off | `case_16` |
| 5 | `arena-scalper` | 5-minute intraday | full | off | `case_04`, `case_08`, `case_09`, `case_17` |
| 6 | `arena-swingsmith` | multi-day swing | full | **on** (auto-close) | `case_01`-`03`, `case_10`, `case_22` |
| 7 | `arena-strider` | slow trend follower | full | off | `case_20` |
| 8 | `arena-rebate-hunter` | high-frequency rebate arbitrage | full | **on** | `case_12` |
| 9 | `arena-autopilot` | fully autonomous LLM | **minimal** | **on** + AI override | `case_13`, `case_14` |
| 10 | `arena-tribunal` | 3-expert jury consensus | jury | off | `case_21` |
| 11 | `arena-dual-signal` | registry fallback (unknown → dual-signal) | **minimal** | off | `case_15` |

Full parameter tables: [docs/STRATEGIES.md](./docs/STRATEGIES.md).

---

## 🛡️ Close-Path Taxonomy

Four mutually-exclusive close paths plus a `none` bucket. Monitors own the first three; the think-node owns `ai_decision`.

| Path | Driven by | Writes |
|---|---|---|
| `stop_loss` | `stop_loss_monitor` (10 s) | `trades(type=close)`, `agent_decisions(trigger=stop_loss)`, delete positions |
| `trailing_stop` | `trailing_stop_monitor` (10 s, when `enable_code_level_protection`) | `trades`, `agent_decisions`, delete positions |
| `partial_profit` | `partial_profit_monitor` (10 s) | partial `trades`, atomic 3-way `UPDATE positions`, `agent_decisions` |
| `ai_decision` | `close_position` / `partial_close` tools (trading loop) | `trades`, atomic three-way `UPDATE positions` |
| `none` | — | open-only or hold snapshots |

Full rules + truth table: [`apps/backend/src/omnitrade/domain/services/close_path_classifier.py`](./apps/backend/src/omnitrade/domain/services/close_path_classifier.py).

---

## 🚀 Get Started

### Path A · Docker (zero setup)

```bash
cp apps/backend/.env.example .env
# edit .env — uncomment LLM_PROVIDER block, set GATE_API_KEY / OKX_API_KEY
docker compose up -d
docker compose exec backend alembic upgrade head   # first run only
```

| URL | Surface |
|---|---|
| `http://localhost:3000` | Next.js dashboard |
| `http://localhost:8000/docs` | FastAPI interactive docs |
| `ws://localhost:8000/ws` | Live account / position / decision events |

### Path B · Local (Python 3.11 + Node 20)

```bash
# Backend
cd apps/backend
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn omnitrade.api.app:create_app --factory --reload

# Frontend (separate terminal)
cd apps/frontend
npm install
npm run dev
```

### Path C · Production

```bash
cp .env.production.example .env.production
# fill secrets — NEVER commit .env.production
docker compose -f docker-compose.prod.yml up -d
```

Full release checklist (smoke tests, observability, rollback plan): [docs/RELEASE_CHECKLIST.md](./docs/RELEASE_CHECKLIST.md).

### Prerequisites

- **LLM API key** — any OpenAI-compatible provider via LiteLLM (DeepSeek, OpenAI, Anthropic, Qwen, Moonshot, …)
- **Exchange credentials** — Gate.io or OKX; **testnet recommended**
- Python 3.11+ with [`uv`](https://github.com/astral-sh/uv) for Path B
- Docker + Docker Compose for Paths A / C

---

## 🧠 Environment

All config is env-driven — see [`apps/backend/.env.example`](./apps/backend/.env.example) (dev) and [`.env.production.example`](./.env.production.example) (prod).

| Variable | Default | Description |
|---|---|---|
| `TRADING_STRATEGY` | `arena-autopilot` | one of 11 strategies |
| `TRADING_INTERVAL_MINUTES` | `20` | cron for the main trading loop |
| `MAX_LEVERAGE` | `25` | hard cap per position |
| `MAX_POSITIONS` | `5` | concurrent open positions |
| `MAX_HOLDING_HOURS` | `36` | force-close after this many hours |
| `EXTREME_STOP_LOSS_PERCENT` | `-30` | hard floor — force-close below this PnL % |
| `EXCHANGE` | `gate` | `gate` or `okx` |
| `GATE_USE_TESTNET` / `OKX_USE_TESTNET` | `true` | **testnet default — live trading requires `false`** |
| `LLM_PROVIDER` | `deepseek` | LiteLLM routing key |
| `LLM_MODEL_NAME` | `deepseek/deepseek-v3.2-exp` | any OpenAI-compatible model |
| `MULTI_AGENT_ENABLED` | `false` | enable `arena-raider-squad` / `arena-tribunal` dispatch |
| `FEE_REBATE_PERCENT` | `20` | shown as `rebateAmount` in `/api/account` |

Full list (40+ variables): [`apps/backend/.env.example`](./apps/backend/.env.example).

### Recommended LLMs

OmniTrade is a **tool-calling-heavy** agent — open/close/partial decisions all flow through OpenAI-style tool calls. Model choice directly decides whether the agent *uses* its tools or fabricates decisions.

| Tier | Examples | When to use |
|---|---|---|
| **Best** | `anthropic/claude-sonnet-4.6`, `openai/gpt-5.4`, `google/gemini-3.1-pro` | Multi-agent swarms (`arena-raider-squad`, `arena-tribunal`), long-running research |
| **Sweet spot** (default) | `deepseek/deepseek-v3.2-exp`, `x-ai/grok-4`, `z-ai/glm-5`, `moonshotai/kimi-k2`, `qwen3-max` | Daily driver — reliable tool-calling at ~1/10 the cost |
| **Avoid** | `*-nano`, `*-flash-lite`, small distilled variants | Tool-calling is unreliable; agent will "answer from memory" instead of querying markets |

---

## 🏛️ Architecture

Classic DDD 4-layer + `agents/`, with monitors carved out as the only layer that composes `domain/` + `infrastructure/` directly (atomicity waiver).

```mermaid
flowchart TD
    api[api<br/>FastAPI + middleware + DI]
    app[application<br/>services, monitors, orchestrators]
    dom[(domain<br/>entities, protocols, pure services)]
    infra[infrastructure<br/>SQLAlchemy, ccxt, LiteLLM, sqlite-vec]
    agents[agents<br/>LangGraph think_node, jury, team experts]

    api --> app
    app --> dom
    app --> agents
    infra --> dom
    agents --> dom

    classDef dom fill:#fef3c7,stroke:#f59e0b
    class dom dom
```

Five async loops, all driven by a single injected `Clock` protocol:

```mermaid
flowchart LR
    L1[trading_loop<br/>cron */TRADING_INTERVAL] --> DB[(SQLite)]
    L2[account_recorder<br/>cron */ACCOUNT_INTERVAL] --> DB
    L3[trailing_stop<br/>10 s] --> DB
    L4[stop_loss<br/>10 s] --> DB
    L5[partial_profit<br/>10 s atomic 3-way UPDATE] --> DB
    style L5 stroke:#dc2626,stroke-width:3px
```

Deep-dive: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md).

---

## 🌐 API Reference

```bash
uv run uvicorn omnitrade.api.app:create_app --factory
# or: docker compose exec backend ...
```

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` · `/api/ready` | liveness / readiness probes |
| `GET` | `/api/account` | balance + rolling 24 h rebate trace |
| `GET` | `/api/positions` | open positions with three-way state |
| `GET` | `/api/trades` | trade history |
| `GET` | `/api/decisions` | agent decision audit log |
| `GET` | `/api/history` | account-value time series |
| `GET` | `/api/stats` | Sharpe, drawdown, strategy breakdown |
| `GET` | `/api/prices` | cached tickers |
| `GET` | `/api/strategy` · `/api/config` | active strategy + runtime knobs |
| `GET` | `/api/rebate` | 24 h rebate summary |
| `GET` | `/api/logs` | in-memory log buffer (tailable) |
| `POST` | `/api/actions/close-all` | emergency close-all (guarded) |
| `WS` | `/ws` | streaming `account` / `position` / `decision` events |

Interactive docs: `http://localhost:8000/docs`.

---

## 🗂️ Project Structure

```
llmtrading/
├── apps/
│   ├── backend/                      # Python 3.11 + FastAPI + SQLAlchemy 2.0
│   │   ├── src/omnitrade/
│   │   │   ├── domain/               # entities, protocols, pure services
│   │   │   ├── application/          # services, 5 monitors, multi-agent
│   │   │   ├── infrastructure/       # SQLAlchemy, ccxt, LiteLLM, WS
│   │   │   ├── agents/               # LangGraph think_node, prompts
│   │   │   └── api/                  # FastAPI routers + middleware
│   │   ├── alembic/                  # migrations (0001 init, 0002 rename)
│   │   └── tests/                    # 642 green (≥ 0.95 characterization)
│   └── frontend/                     # Next.js 14 + SWR + WebSocket
├── tests/fixtures/frozen/            # 22 hand-curated decision contracts
├── docs/                             # architecture, strategies, release, ...
├── scripts/                          # ops + characterization CLI
└── docker-compose.yml                # backend + frontend + sqlite
```

---

## 🛤️ Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0-7 | DDD port, monitors, dashboard, observability | ✅ shipped |
| 8.x | Port-boundary stubs, multi-timeframe, LLM tools, multi-agent orchestrator, WebSocket market stream | ✅ shipped |
| 9.x | Zero-share rebrand (strategy names, schema columns, fixture IDs, brand sentinel) | ✅ shipped |
| 10.x | License inventory, provenance audit, history scrub | ✅ shipped |
| 11 | Postgres + Decimal/Numeric precision, observability events, per-strategy sub-agent cassettes | 📋 planned |

---

## 🤝 Contributing

Issues and PRs welcome. Please:

1. Run `uv run pytest` inside `apps/backend` — the **642-test suite must stay green**, and the 22 frozen fixtures must replay at ≥ 0.95.
2. Respect the **LangGraph scope constraint** — only `agents/think_node.py` is allowed to import `langgraph`.
3. Respect the **three-way state atomicity** — any code path that writes a position's `cumulative_close_pct`, `stop_loss`, or `trailing_peak_pnl_pct` must go through `PositionRepository.apply_three_way_state`.
4. Keep new dependencies within the allow-list (MIT / Apache-2.0 / BSD / ISC / MPL-2.0). See [docs/LICENSE_INVENTORY.md](./docs/LICENSE_INVENTORY.md).

---

## 📄 License

MIT — see [LICENSE](./LICENSE).

---

## ⚠️ Disclaimer

Testnet is the default and the recommended mode. Live trading on mainnet carries a real risk of total loss of funds. The maintainers are **not financial advisors**; nothing in this repository constitutes financial advice. Use at your own risk.
