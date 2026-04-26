<p align="center">
  <b>English</b> | <a href="README_ZH.md">简体中文</a>
</p>

<p align="center">
  <a href="https://github.com/gong1414/omnitrade"><img src="assets/logo-horizontal.svg" alt="OmniTrade" width="520"></a>
</p>

<h1 align="center">OmniTrade: LLM-Driven Crypto Futures Arena</h1>

<p align="center">
  <b>11 competing strategies · 4 close-path taxonomy · atomic three-way state · real-time dashboard</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-Next.js%2014-000000?style=flat&logo=next.js&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/Agent-Agno%20%2B%20AgentOS-8A2BE2?style=flat" alt="Agno">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat" alt="License"></a>
  <br>
  <img src="https://img.shields.io/badge/Strategies-11-FF6B6B" alt="Strategies">
  <img src="https://img.shields.io/badge/Close_Paths-4%2B1-4ECDC4" alt="Close Paths">
  <img src="https://img.shields.io/badge/Frozen_Fixtures-22%2F22-FFD93D" alt="Fixtures">
  <img src="https://img.shields.io/badge/Tests-702_green-2BB673" alt="Tests">
  <img src="https://img.shields.io/badge/Exchanges-Gate%20%2B%20OKX-F6465D" alt="Exchanges">
  <br>
  <a href="https://github.com/gong1414/omnitrade/stargazers"><img src="https://img.shields.io/github/stars/gong1414/omnitrade?style=flat&logo=github&color=FFD43B" alt="GitHub stars"></a>
  <a href="https://github.com/gong1414/omnitrade/network/members"><img src="https://img.shields.io/github/forks/gong1414/omnitrade?style=flat&logo=github&color=4F8BC9" alt="GitHub forks"></a>
  <a href="https://github.com/gong1414/omnitrade/issues"><img src="https://img.shields.io/github/issues/gong1414/omnitrade?style=flat&logo=github&color=FF6B6B" alt="GitHub issues"></a>
  <a href="https://github.com/gong1414/omnitrade/releases/latest"><img src="https://img.shields.io/github/v/release/gong1414/omnitrade?style=flat&logo=github&include_prereleases&color=8A2BE2" alt="GitHub release"></a>
  <a href="https://github.com/gong1414/omnitrade/commits/main"><img src="https://img.shields.io/github/last-commit/gong1414/omnitrade?style=flat&logo=github&color=2BB673" alt="last commit"></a>
  <a href="https://codecov.io/gh/gong1414/omnitrade"><img src="https://img.shields.io/codecov/c/github/gong1414/omnitrade?style=flat&logo=codecov" alt="Codecov"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/gong1414/omnitrade"><img src="https://api.securityscorecards.dev/projects/github.com/gong1414/omnitrade/badge" alt="OpenSSF Scorecard"></a>
</p>

<p align="center">
  <a href="#-news">News</a> &nbsp;&middot;&nbsp;
  <a href="#-try-in-2-minutes">Try in 2 Min</a> &nbsp;&middot;&nbsp;
  <a href="#-key-features">Features</a> &nbsp;&middot;&nbsp;
  <a href="#-strategies">Strategies</a> &nbsp;&middot;&nbsp;
  <a href="#-omnitrade-vs-hand-rolled-setups">vs Hand-rolled</a> &nbsp;&middot;&nbsp;
  <a href="#-get-started">Get Started</a> &nbsp;&middot;&nbsp;
  <a href="#-architecture">Architecture</a> &nbsp;&middot;&nbsp;
  <a href="#-api-reference">API</a> &nbsp;&middot;&nbsp;
  <a href="#-sponsorship--support-the-project">Sponsor</a> &nbsp;&middot;&nbsp;
  <a href="#-license">License</a>
</p>

---

## 📢 Project Status

OmniTrade is **actively developed**. The architecture, API surface, and
strategies all evolve in response to operator feedback — issues and
feature requests are very welcome and treated as first-class signal.

If anything breaks, feels off, or you'd like to see a new strategy /
data source / dashboard panel, please [open an issue][issues] or a
pull request — see [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow
and [SECURITY.md](SECURITY.md) for vulnerability reports (private
channel only). Star the repo if you'd like to follow along.

[issues]: https://github.com/gong1414/omnitrade/issues

---

## ⚠️ Risk Disclaimer — please read before running

OmniTrade automates real trades on cryptocurrency exchanges. Crypto
derivatives are high-leverage instruments and can cost you the entire
balance of an account in a single bad cycle. This project is research
software released under the MIT license, with **no warranty of any kind**.
The maintainers are not financial advisors and accept no liability for
any losses incurred from running it.

By using this software you accept that:

- **You are responsible for every trade it places.** The agent will open,
  size, and close positions autonomously. Treat its decisions as your
  own.
- **Start on testnet.** `GATE_USE_TESTNET=true` and `OKX_USE_TESTNET=true`
  are the defaults. Run for weeks on testnet before flipping either flag.
- **Start small on mainnet.** When you do go live, begin with a balance
  you would be willing to lose entirely. The HITL gate
  (`HITL_OPEN_SIZE_THRESHOLD_USD`, default $10 000) is a safety net, not
  a substitute for setting your own position-size limits.
- **Lock down your exchange API keys.** Set them to "trade only, no
  withdraw" on Gate.io / OKX. Enable 2FA on the exchange account.
- **Monitor it.** The dashboard exposes every cycle's reasoning,
  positions, and gates. Read it. The G5 fault-phrase scanner flags
  obvious problems automatically; subtler issues are still your call.
- **You bear full regulatory risk.** Algorithmic trading of crypto
  derivatives may be restricted or prohibited in your jurisdiction —
  verify your local rules before running this software.

If you can't accept those terms, stop here.

---

## 📰 News

- **2026-04-26** 🎉 **Open-source release `v0.1.0`** — Agno cutover (Stages A–E) + T1–T10 hardening all green. Full release notes at [v0.1.0](https://github.com/gong1414/omnitrade/releases/tag/v0.1.0).
- **2026-04-26** 🛡️ **OSS quality batch** — Dependabot + CodeQL security scanning, branch protection on main, GitHub Pages live at [docs](https://gong1414.github.io/omnitrade/), full ADR collection under [`docs/adr/`](docs/adr/).
- **2026-04-26** 📚 **Quickstart + FAQ** — `git clone → first cycle in <5 min` walkthrough at [`docs/QUICKSTART.md`](docs/QUICKSTART.md), 11 common errors covered in [`docs/FAQ.md`](docs/FAQ.md).
- **2026-04-26** 🤖 **T10 — Trade-journal RAG** — every cycle's structured reasoning is now ingested into `ai.trade_journal` (PgVector hybrid search) and auto-injected as context into subsequent cycles. Default embedder is local `BAAI/bge-small-en-v1.5` (no API key needed).
- **2026-04-26** 🛑 **T9 — HITL large-open gate** — opens above `HITL_OPEN_SIZE_THRESHOLD_USD` (default $10 000) pause via SSE and require operator approval through the dashboard banner.
- **2026-04-26** 🔭 **T4 — OpenTelemetry tracing** — every Agno run / model call / tool call emits a span via OpenInference's `AgnoInstrumentor`; visit `GET /traces` for the per-cycle span tree.

---

## ⚡ Try in 2 Minutes

The shortest path from `git clone` to "the agent is trading on Gate.io
testnet", in one paste-able block:

```bash
git clone https://github.com/gong1414/omnitrade.git && cd omnitrade && \
  cp apps/backend/.env.example .env && \
  echo "Edit .env now: set LLM_API_KEY (DeepSeek), GATE_API_KEY, GATE_API_SECRET" && \
  docker compose up -d && \
  curl -X POST http://localhost:8000/api/v1/cycle/trigger
```

Then open `http://localhost:3000/dashboard`. Full walkthrough at
[`docs/QUICKSTART.md`](docs/QUICKSTART.md); common errors at
[`docs/FAQ.md`](docs/FAQ.md).

---

## 💡 What Is OmniTrade?

OmniTrade is an autonomous **crypto-futures trading arena** where 11 LLM-driven strategies compete for PnL on Gate.io or OKX perpetuals. Point it at a testnet, pick a strategy, and watch the agent reason about markets, size positions, and manage risk — with every decision verifiable via a structured output contract test suite.

### Key Capabilities

- **11 named strategies** — from `arena-guardian` (capital-preservation) through `arena-raider-squad` (multi-agent attack team) to `arena-autopilot` (fully autonomous LLM)
- **4-path close-path taxonomy** — `stop_loss`, `trailing_stop`, `partial_profit`, `ai_decision`, plus `none`; enforced by a pure classifier and three 10-second monitors
- **Atomic three-way state contract** — `cumulative_close_pct`, `stop_loss`, `trailing_peak_pnl_pct` land in a single SQL `UPDATE` so the stop-loss monitor can never read a torn write
- **Testnet by default** — `GATE_USE_TESTNET=true` / `OKX_USE_TESTNET=true` out of the box; live trading requires explicit override
- **Characterization gate** — 22 frozen fixtures replay deterministically at ≥ 0.95 Decision-equivalent pass rate
- **Real-time dashboard** — Next.js 14 App Router + SWR + Server-Sent Events (EventSource) with exponential-backoff reconnect

---

## 🎯 Who It Is For

- **LLM agent researchers** who want a non-toy benchmark — real exchange API, structured tool-calling under cost pressure, multi-agent coordination on a single PnL-driven loop.
- **Quant tinkerers** who treat "AI manages crypto futures" as a hobby project and want a complete stack to play with rather than building from scratch.
- **Operators on testnet** who want to study how an LLM behaves on real market data over weeks, before considering any mainnet exposure.
- **Tooling/MCP authors** who want a working example of `MultiMCPTools` driving 15 tools (9 trading + 6 crypto-data) under Agno.

OmniTrade is **not** for: people who want a turnkey money printer, traders looking for a copy-trade signal service, or anyone who can't afford to lose every dollar in the account.

## 🔬 Use Cases

- **Paper-trade an LLM** for weeks on Gate.io / OKX testnet, then read every cycle's reasoning to develop intuition for what the model actually understands.
- **Compare strategies** — run the same market window through `arena-guardian` vs `arena-raider` vs `arena-tribunal` and see how different prompt branches handle the same setup.
- **Test new MCP tools** — drop a new FastMCP server in `infrastructure/mcp/`, register it via `MultiMCPTools`, and watch the agent discover and call it.
- **Stress-test agent reliability** — the `T7 ReliabilityEval` lane and `T8 AccuracyEval` lane catch regressions in tool-calling fidelity (the "did the agent actually use its tools or fabricate the answer?" axis).
- **Run a personal account on mainnet** — only after weeks of testnet plus your own conviction. Treat it as a colleague who needs supervision, not an autopilot.

## ⚖️ OmniTrade vs Hand-rolled Setups

| Typical hand-rolled setup | OmniTrade |
|---|---|
| LLM in one Jupyter notebook + ccxt in another + a Postgres dump for trade history | Single-process FastAPI + AgentOS scheduler + Postgres + pgvector + 6 fast monitors, all in `docker compose up` |
| Mocked tests pass, prod migrations break | 22 frozen-fixture replays at ≥ 0.95 + integration tests that hit real SQLite/Postgres (no mocked DB) |
| LLM hallucinates positions; you only notice on the next bill | G6 cross-source consistency check + G5 fault-phrase guardrail; phantom positions trip the build, not the wallet |
| Stop-loss and partial-close races corrupt position state | Three-way state atomic write contract — `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` land in one SQL `UPDATE` |
| Large unintended opens slip through unattended | T9 HITL gate pauses opens > `HITL_OPEN_SIZE_THRESHOLD_USD` (default $10 000) via SSE — operator approves on the dashboard |
| LLM reasoning is forgotten between sessions | T10 trade-journal RAG ingests every decision into PgVector; subsequent cycles see semantically relevant prior decisions in their system prompt |
| No visibility into "did the agent really use its tools?" | OpenTelemetry traces (T4) — one span per Agent.arun / model call / tool call, served via AgentOS `GET /traces` |
| Multi-framework drift (LangChain + LiteLLM + LangGraph + mcp2py) | One framework — Agno 2.x. CI's Acceptance 4 enforces zero legacy imports |

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
        • Real-time dashboard via Server-Sent Events (single transport)<br>
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

11 strategies, each a concrete configuration of **leverage band → trailing ladder → partial-profit stages → stop-loss override → system-prompt branch**. Quick names: `arena-guardian` / `arena-steward` / `arena-raider` / `arena-raider-squad` / `arena-scalper` / `arena-swingsmith` / `arena-strider` / `arena-rebate-hunter` / `arena-autopilot` / `arena-tribunal` / `arena-dual-signal`.

<details>
<summary><b>Click to expand the full 11-strategy table</b></summary>

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

</details>

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
# edit .env — set LLM_API_KEY (DeepSeek), GATE_API_KEY / OKX_API_KEY, leave testnet flags ON
docker compose up -d
# `db-init` runs `alembic upgrade head` automatically and the backend
# waits on `service_completed_successfully` before starting.
```

Verify the cycle is running end-to-end:

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger          # should return {"status":"ok"} in ≤60s
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq    # last decision JSON
```

| URL | Surface |
|---|---|
| `http://localhost:3000/dashboard` | Next.js dashboard |
| `http://localhost:8000/docs` | FastAPI interactive docs |
| `http://localhost:8000/sse/stream` | Server-Sent Events feed (decision / position / run-paused) |

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

- **LLM API key** — DeepSeek (default `deepseek-reasoner`; switch to `deepseek-v4-pro` / `-flash` via `AGNO_LLM_MODEL`), driven directly by Agno's DeepSeek model class
- **Exchange credentials** — Gate.io or OKX; **testnet recommended**
- Python 3.11+ with [`uv`](https://github.com/astral-sh/uv) for Path B
- Docker + Docker Compose for Paths A / C

---

## 🧠 Environment

All config is env-driven. Two essentials and the rest are documented inline:

- `LLM_API_KEY` — your DeepSeek / OpenAI / OpenRouter key
- `GATE_API_KEY` + `GATE_API_SECRET` — exchange credentials (testnet default)

Full reference (40+ variables) lives in [`apps/backend/.env.example`](./apps/backend/.env.example) with documenting comments per row.

<details>
<summary><b>Click for the most-asked variables (defaults shown)</b></summary>

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
| `LLM_PROVIDER` | `deepseek` | Agno DeepSeek provider key |
| `LLM_MODEL_NAME` | `deepseek/deepseek-v3.2-exp` | any OpenAI-compatible model |
| `MULTI_AGENT_ENABLED` | `false` | enable `arena-raider-squad` / `arena-tribunal` dispatch |
| `FEE_REBATE_PERCENT` | `20` | shown as `rebateAmount` in `/api/account` |
| `HITL_OPEN_SIZE_THRESHOLD_USD` | `10000` | T9 — opens above this pause for operator approval |
| `EMBEDDER_PROVIDER` | `fastembed` | `fastembed` (local, default) or `openai` |
| `OTEL_TRACING_ENABLED` | `true` | T4 — OpenTelemetry span emission |

</details>

<details>
<summary><b>Recommended LLMs (model-choice cheat sheet)</b></summary>

OmniTrade is a **tool-calling-heavy** agent — open/close/partial decisions all flow through OpenAI-style tool calls. Model choice directly decides whether the agent *uses* its tools or fabricates decisions.

| Tier | Examples | When to use |
|---|---|---|
| **Best** | `anthropic/claude-sonnet-4.6`, `openai/gpt-5.4`, `google/gemini-3.1-pro` | Multi-agent swarms (`arena-raider-squad`, `arena-tribunal`), long-running research |
| **Sweet spot** (default) | `deepseek/deepseek-v3.2-exp`, `x-ai/grok-4`, `z-ai/glm-5`, `moonshotai/kimi-k2`, `qwen3-max` | Daily driver — reliable tool-calling at ~1/10 the cost |
| **Avoid** | `*-nano`, `*-flash-lite`, small distilled variants | Tool-calling is unreliable; agent will "answer from memory" instead of querying markets |

</details>

---

## 🏛️ Architecture

Classic DDD 4-layer (`domain` / `application` / `infrastructure` / `api`) + a dedicated `agents/` module that's the only place allowed to import Agno. Five async loops drive everything: one trading cycle (AgentOS-scheduled) plus four 10-second monitors that own the position-protection paths.

Deep-dive with full mermaid diagrams + scheduler topology + three-way state invariant: **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** ([中文](./docs/ARCHITECTURE_ZH.md)).

<details>
<summary><b>Click for layer + scheduler diagrams</b></summary>

```mermaid
flowchart TD
    api[api<br/>FastAPI + middleware + DI]
    app[application<br/>services, monitors, orchestrators]
    dom[(domain<br/>entities, protocols, pure services)]
    infra[infrastructure<br/>SQLAlchemy, ccxt, Agno DeepSeek, sqlite-vec]
    agents[agents<br/>Agno Agent + MultiMCPTools + Team]

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
    L1[trading_loop<br/>AgentOS scheduler */TRADING_INTERVAL] --> DB[(Postgres + pgvector)]
    L2[account_recorder<br/>cron */ACCOUNT_INTERVAL] --> DB
    L3[trailing_stop<br/>10 s] --> DB
    L4[stop_loss<br/>10 s] --> DB
    L5[partial_profit<br/>10 s atomic 3-way UPDATE] --> DB
    style L5 stroke:#dc2626,stroke-width:3px
```

</details>

---

## 🌐 API Reference

Interactive Swagger docs: `http://localhost:8000/docs` (renders the live spec). Every public route is read-only except `POST /api/v1/cycle/trigger`, `POST /api/v1/runs/{id}/{confirm,reject}` (T9 HITL), and `POST /api/actions/close-all` (password-gated emergency).

<details>
<summary><b>Click for the full endpoint table</b></summary>

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
| `POST` | `/api/v1/cycle/trigger` | trigger one trading cycle synchronously |
| `POST` | `/api/v1/runs/{run_id}/confirm` · `/reject` | T9 HITL approve / reject a paused large open |
| `GET` | `/sse/stream` | Server-Sent Events feed (`decision_update`, `position_update`, `run_paused`, `orchestrator_error`, …) |
| `GET` | `/traces` | AgentOS-served OTel span tree per cycle (T4) |

The same routes are also reachable under the `/api/v1/*` prefix; the unprefixed `/api/*` surface is the Phase-8 legacy mount and is kept for the dashboard's existing fetch URLs.

</details>

---

## 🗂️ Project Structure

Two apps in a monorepo: `apps/backend/` (Python 3.11 / FastAPI / Agno) and `apps/frontend/` (Next.js 14). Shared infra in `docker-compose.yml`. Strategy + architecture deep-dives under `docs/`.

<details>
<summary><b>Click for the full directory tree</b></summary>

```
omnitrade/
├── apps/
│   ├── backend/                      # Python 3.11 + FastAPI + SQLAlchemy 2.0
│   │   ├── src/omnitrade/
│   │   │   ├── domain/               # entities, protocols, pure services
│   │   │   ├── application/          # services, 5 monitors, multi-agent
│   │   │   ├── infrastructure/       # SQLAlchemy, ccxt, Agno DeepSeek, SSE
│   │   │   ├── agents/               # Agno Agent + MultiMCPTools, prompts
│   │   │   └── api/                  # FastAPI routers + middleware
│   │   ├── alembic/                  # migrations
│   │   └── tests/                    # structured output + integration tests
│   └── frontend/                     # Next.js 14 + SWR + Server-Sent Events
├── tests/fixtures/frozen/            # 22 hand-curated decision contracts
├── docs/                             # architecture, strategies, release, ADRs
├── assets/                           # logo + social preview + sponsor QR
├── scripts/                          # ops + drift-detection probes
└── docker-compose.yml                # postgres + pgvector + db-init + backend + frontend
```

</details>

---

## 🛤️ Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0-7 | DDD port, monitors, dashboard, observability | ✅ shipped |
| 8.x | Port-boundary stubs, multi-timeframe, LLM tools, multi-agent orchestrator, WebSocket market stream | ✅ shipped (WS replaced by SSE in Agno cutover) |
| 9.x | Zero-share rebrand (strategy names, schema columns, fixture IDs, brand sentinel) | ✅ shipped |
| 10.x | License inventory, provenance audit, history scrub | ✅ shipped |
| 11 | Postgres + Decimal/Numeric precision, observability events, per-strategy sub-agent cassettes | 📋 planned |

---

## 🤝 Contributing

Issues and PRs welcome. Please:

1. Run `uv run pytest` inside `apps/backend` — the **702-test suite must stay green**, and the 22 frozen fixtures must replay at ≥ 0.95.
2. The Agno cutover (Stages A–E, see `docs/AGNO_MIGRATION_TRACKER.md`) removed every LangGraph / LangChain / LiteLLM / mcp2py / WebSocket consumer — keep them out of new code.
3. Respect the **three-way state atomicity** — any code path that writes a position's `cumulative_close_pct`, `stop_loss`, or `trailing_peak_pnl_pct` must go through `PositionRepository.apply_three_way_state`.
4. Keep new dependencies within the allow-list (MIT / Apache-2.0 / BSD / ISC / MPL-2.0). See [docs/LICENSE_INVENTORY.md](./docs/LICENSE_INVENTORY.md).

---

## 💖 Sponsorship — support the project

OmniTrade is a solo / volunteer-maintained open-source project. If it
saves you time or makes you money on testnet (and eventually
mainnet), a small tip is genuinely appreciated — it pays for LLM API
credits, server time, and the occasional tank of caffeine.

**USDT (Tron · TRC20)**

```
TMDnFG8KBxNvkgNgqkr9PhL2keNczjSGdS
```

<a href="assets/sponsor-usdt-trc20.svg">
  <img src="assets/sponsor-usdt-trc20.svg" alt="USDT TRC20 QR code" width="200" />
</a>

> **⚠️ Network warning**: This is a **TRON (TRC20)** address. Sending
> USDT (or anything else) on a different network — Ethereum / ERC20,
> BSC / BEP20, Polygon, Arbitrum, Solana, etc. — will result in **lost
> funds with no recovery**. Verify your wallet is set to *Tron* before
> sending. Always copy-paste the address; a single character changed
> is a different wallet.

No expectation, no obligation, no donor list, no tax-deductible
guarantees — just a way for people who want to say thanks. If you'd
prefer to support via GitHub Sponsors / Open Collective once those
are set up, [open an issue](https://github.com/gong1414/omnitrade/issues)
to nudge.

---

## 🌟 Stargazers & contributors

[![Star History Chart](https://api.star-history.com/svg?repos=gong1414/omnitrade&type=Date)](https://www.star-history.com/#gong1414/omnitrade&Date)

<a href="https://github.com/gong1414/omnitrade/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=gong1414/omnitrade" alt="Contributors" />
</a>

---

## 📄 License

MIT — see [LICENSE](./LICENSE).

---

## ⚠️ Disclaimer

Testnet is the default and the recommended mode. Live trading on mainnet carries a real risk of total loss of funds. The maintainers are **not financial advisors**; nothing in this repository constitutes financial advice. Use at your own risk.

---

## 🙏 Acknowledgments — built on the shoulders of these projects

OmniTrade is built on ~30 open-source projects — full stack from agent runtime (Agno + FastMCP + OpenInference) to backend (FastAPI + SQLAlchemy + Postgres + pgvector + ccxt) to frontend (Next.js + React + Tailwind + Recharts) to tooling (uv + Ruff + pytest + Playwright). Huge thanks to all the maintainers — please go star their repos.

<details>
<summary><b>Click for the full acknowledgments list</b></summary>

**Agent runtime**
- [**Agno**](https://github.com/agno-agi/agno) — the Agent / Team / Workflow / AgentOS layer that drives every cycle. Single source of truth after the cutover.
- [**FastMCP**](https://github.com/jlowin/fastmcp) — the MCP server framework powering the 9 trading + 6 crypto-data tools.
- [**OpenInference**](https://github.com/Arize-ai/openinference) — the `AgnoInstrumentor` that turns Agno run / model / tool calls into OpenTelemetry spans.
- [**OpenTelemetry**](https://github.com/open-telemetry) — the tracing API + SDK behind `GET /traces`.

**LLM + embeddings**
- [**DeepSeek**](https://www.deepseek.com/) — the default chat model (`deepseek-v4-pro` / `-flash` / `-reasoner`) — fast, cheap, reliable tool-calling.
- [**fastembed**](https://github.com/qdrant/fastembed) + [**BAAI/bge-small-en-v1.5**](https://huggingface.co/BAAI/bge-small-en-v1.5) — local 384-dim embedder for the trade-journal RAG.
- [**hf-mirror.com**](https://hf-mirror.com/) — community-run HuggingFace mirror that makes fastembed reachable on cn networks.

**Backend**
- [**FastAPI**](https://github.com/fastapi/fastapi) + [**Uvicorn**](https://github.com/encode/uvicorn) — the HTTP / SSE surface.
- [**SQLAlchemy**](https://github.com/sqlalchemy/sqlalchemy) + [**Alembic**](https://github.com/sqlalchemy/alembic) — async ORM + migrations.
- [**Postgres**](https://www.postgresql.org/) + [**pgvector**](https://github.com/pgvector/pgvector) — primary store + vector index for the trade-journal Knowledge layer.
- [**psycopg**](https://github.com/psycopg/psycopg) (3.x) — single sync+async driver routed through SQLAlchemy.
- [**APScheduler**](https://github.com/agronholm/apscheduler) — drives the 6 fast position-protection monitors at 10s cadence.
- [**ccxt**](https://github.com/ccxt/ccxt) — unified Gate.io / OKX adapter.
- [**structlog**](https://github.com/hynek/structlog) — the structured-JSON logging layer with secret-stripping processors.
- [**pydantic**](https://github.com/pydantic/pydantic) + [**pydantic-settings**](https://github.com/pydantic/pydantic-settings) — config + every schema in `domain/`.

**Frontend**
- [**Next.js 14**](https://github.com/vercel/next.js) — App Router dashboard.
- [**React**](https://github.com/facebook/react) — UI runtime.
- [**Tailwind CSS**](https://github.com/tailwindlabs/tailwindcss) — design system.
- [**Recharts**](https://github.com/recharts/recharts) — the equity-curve & confidence-gauge charts.
- [**SWR**](https://github.com/vercel/swr) — data fetching for non-streaming endpoints.

**Tooling**
- [**uv**](https://github.com/astral-sh/uv) — Python package manager (10-100× faster than pip).
- [**Ruff**](https://github.com/astral-sh/ruff) — lint + format.
- [**pytest**](https://github.com/pytest-dev/pytest) + [**vcrpy**](https://github.com/kevin1024/vcrpy) — test runner + cassette-based HTTP record/replay.
- [**vitest**](https://github.com/vitest-dev/vitest) + [**Playwright**](https://github.com/microsoft/playwright) — frontend unit + E2E tests.
- [**Docker**](https://www.docker.com/) / [**OrbStack**](https://orbstack.dev/) — local stack runtime.

**Crypto data sources** — read-only, free or freemium:
[CoinGecko](https://www.coingecko.com/), [Alternative.me Fear & Greed](https://alternative.me/crypto/fear-and-greed-index/), [Whale Alert](https://whale-alert.io/), [Coinglass](https://www.coinglass.com/), [LunarCrush](https://lunarcrush.com/), [Etherscan](https://etherscan.io/), [Gate MCP News](https://api.gatemcp.ai/mcp/news).

</details>

If we missed your project, please [open an issue][issues] and we'll add
you in.
