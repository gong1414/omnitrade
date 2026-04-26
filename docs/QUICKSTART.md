# Quickstart — first cycle in 5 minutes

> English · [简体中文](QUICKSTART_ZH.md)

This is the shortest possible path from "git clone" to "the agent is
trading on Gate.io testnet". Every step is one command. If you hit a
problem, jump to [docs/FAQ.md](FAQ.md) — the common errors are listed
there with copy-pasteable fixes.

> ⚠️ **Testnet only** for the first run. Mainnet trading needs a deliberate
> `GATE_USE_TESTNET=false` flip and we recommend weeks of testnet runtime
> before that. See [SECURITY.md](../SECURITY.md) and the README's risk
> disclaimer.

## Prerequisites

- Docker + Docker Compose ([OrbStack](https://orbstack.dev/) on macOS works great)
- A DeepSeek API key — sign up at https://platform.deepseek.com (~30 sec, no payment needed for testnet keys)
- A Gate.io **testnet** account — https://www.gate.io/testnet (use it for free testnet USDT)

## 1. Clone

```bash
git clone https://github.com/gong1414/omnitrade.git
cd omnitrade
```

## 2. Configure

```bash
cp apps/backend/.env.example .env
```

Open `.env` in your editor and fill in the **only three** keys you actually
need to start:

| Key | Where to get |
|---|---|
| `LLM_API_KEY` | https://platform.deepseek.com → API keys |
| `GATE_API_KEY` | Gate.io testnet → Account → API |
| `GATE_API_SECRET` | same page |

Leave everything else at the defaults. `GATE_USE_TESTNET=true` is already
set, so you're sandboxed by default.

## 3. Boot the stack

```bash
docker compose up -d
```

This brings up Postgres + pgvector, runs Alembic migrations once, then
starts the backend (FastAPI + AgentOS) and the frontend (Next.js).
First boot takes ~3 minutes (image build + downloading the
`BAAI/bge-small-en-v1.5` embedder via the Chinese HF mirror).

Verify the backend is alive:

```bash
curl -fsS http://localhost:8000/health
# → {"status":"ok"}
```

## 4. Trigger the first cycle

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger
# → {"status":"ok","elapsed_seconds":42}
```

## 5. Read the result

```bash
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq
```

You should see a `StructuredReason` JSON with `market_context`,
`gates_passed`, `invalidation_condition`, `plan`, `confidence`,
`justification`, and `output_language` populated.

## 6. Open the dashboard

```
http://localhost:3000/dashboard
```

The latest cycle's reasoning renders in the 5-panel layout (Market
Context / Gates / Invalidation / Plan / ConfidenceGauge). Subsequent
cycles fire automatically every `TRADING_INTERVAL_MINUTES` (default 20).

---

## What to do next

- **Pick a different strategy** — set `TRADING_STRATEGY` in `.env` to one
  of the 11 names listed in `docs/STRATEGIES.md`, then
  `docker compose restart backend`.
- **Tighten the safety net** — lower `HITL_OPEN_SIZE_THRESHOLD_USD` in
  `.env` (default $10 000) to whatever notional you want to physically
  approve. Opens above the threshold pause for manual approval via the
  dashboard banner.
- **Watch traces** — `http://localhost:8000/traces` shows the
  per-cycle OpenTelemetry span tree (every Agno tool call, model call,
  hook).
- **Read every cycle's justification** — the AI's `gates_passed` and
  `justification` are a free QA channel. The G5 fault-phrase scanner
  flags obvious failures automatically; subtler issues are still your
  call.

## Going to mainnet

We strongly recommend **weeks of testnet** before flipping. When you do:

1. Set `GATE_USE_TESTNET=false`
2. Drop `INITIAL_BALANCE_USDT` to a meaningful-but-recoverable amount
3. Set the Gate.io API key to "trade only, no withdraw"
4. Walk the [G1–G6 acceptance gates](../CLAUDE.md) before you stop watching it

If you hit a problem the FAQ doesn't cover, please
[open an issue](https://github.com/gong1414/omnitrade/issues/new/choose).
