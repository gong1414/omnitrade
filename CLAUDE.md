# OmniTrade — Project-Level Rules for Claude

This file is picked up automatically when working in this repo. It encodes
permanent process rules earned from real failures; do not soften or bypass
them without the user's explicit approval.

---

## 🚨 Hard Rule: User-Visible Acceptance Gate (MANDATORY every Phase)

Before declaring any Phase / PR / feature "complete" or "ready", you MUST
walk this entire checklist by hand. Do NOT substitute technical artifacts
(pytest green, rg hygiene, type-check clean, alembic round-trip) for
user-visible verification. Technical green ≠ system works. Learned from
PR-B1/B2: 734 tests passed, 0 cassettes broken — and the user still saw
nothing in the dashboard because scheduler wasn't wired and API wasn't
serializing the new fields.

### Gate G1 — Trigger a real end-to-end cycle

```bash
# Must be a REAL call, not a test mock:
curl -X POST http://localhost:8000/api/v1/cycle/trigger
```

Required: returns `{"status":"ok","elapsed_seconds":<=60}`. If 500 or
timeout, read backend logs and fix root cause before claiming "done".

### Gate G2 — Read the latest decision's full JSON, sanity-check every field

```bash
curl -sS "http://localhost:8000/api/v1/decisions?limit=1" | jq
```

For each field, ask and answer:

- [ ] `positions_count` — does it **match** `/api/v1/positions` response?
      (Earlier bug: AI saw 6 phantom positions while DB had 0.)
- [ ] `market_context` — describes prices that **match current BTC/ETH
      market**? (Open coingecko in another tab, cross-check.)
- [ ] `gates_passed` — each string describes a **plausible signal in the
      current market**? Non-trivial content? (Not `["ok"]`.)
- [ ] `invalidation_condition` — specific, testable condition, not a
      tautology?
- [ ] `plan` — if action=open/partial_close: populated with non-zero
      numbers? if action=hold: null? Check both cases.
- [ ] `structured_confidence` — in [0, 1]? Not NaN? Reasonable given the
      reasoning tone?
- [ ] `output_language` — matches `OUTPUT_LANGUAGE` env var? UI renders
      text in that language?
- [ ] `iteration` — incrementing across cycles?

### Gate G3 — Open the dashboard and verify rendering

```
http://localhost:3000/dashboard
```

- [ ] AgentReasoningFeed shows the newest decision as the first row
- [ ] The 5-panel layout renders (Market Context / Gates / Invalidation /
      Plan / ConfidenceGauge) when structured fields are present
- [ ] Legacy rows (structured fields null) degrade to blockquote
- [ ] Numbers align with the API response (tabular-nums, % direction,
      decimal precision, thousands separator)
- [ ] Switch `OUTPUT_LANGUAGE` zh↔en and see the reasoning text actually
      switch language in the next cycle's output
- [ ] Take a screenshot to `~/Desktop/` to preserve visual proof

### Gate G4 — Observe scheduler stability

- [ ] Let the scheduler run at least 3 full cycles without manual trigger
- [ ] Check `docker compose logs backend --tail 100` for exceptions,
      rate-limit hits, timeout warnings, or cascading errors
- [ ] Verify each cycle produces a new DB row (no silent failures)
- [ ] Confirm cycle cadence matches `TRADING_INTERVAL_MINUTES`

### Gate G5 — Treat AI's reasoning as a QA report

**CRITICAL**: If AI's `market_context` / `gates_passed` / `justification`
contains any of these phrases, treat as a BUG TICKET, not LLM noise:

- "异常", "错误", "不符合", "不正常", "数据同步故障"
- "anomaly", "error", "inconsistent", "malformed", "data sync issue"
- "system issue", "系统异常", "数据异常"
- "所有 X 都是 0", "all X are 0/null/empty"

The Phase-C phantom-positions bug was reported verbatim by the LLM in its
decision text and I missed it because I treated the reasoning as
decoration, not as ground truth. **AI is a free QA channel. Read every
word.**

Action when this trips: stop the Phase, investigate what the AI is
pointing at, fix it, re-run the cycle. Do NOT commit until the AI stops
saying "system has issues".

### Gate G6 — Cross-source consistency check

At least one assertion comparing two independent data sources:

- `AI decision's positions_count` vs `GET /api/v1/positions`
- `AI decision's market_context prices` vs `GET /api/v1/prices`
- `AI decision's account_value` vs `GET /api/v1/account`

Disagreement between sources = bug. Silence on this = missed bug.

---

## 🚫 Anti-Patterns (never do these again)

1. **Substituting indicators for behavior**. `pytest PASS` + `rg clean` +
   `alembic round-trip` does not prove the user can USE the feature. A
   complete Phase means a real user-visible round-trip.

2. **Relaxing a failed gate instead of investigating**. When PR-B2 Gate 2
   ("content quality") failed, the right move was "why is hold/close
   legitimately failing this check?". Relaxing the gate definition was
   correct here, but only after articulating *why* the system was right
   and the gate was wrong. Never change the yardstick silently.

3. **Trusting executor summaries without reading their work**. Agents
   routinely report "all green" when they mean "my own tests pass". Read
   the actual output they wrote (especially DB state, commit diff, test
   report). If an agent says "22 cassettes still green", confirm with
   `pytest tests/behavioral_equivalence/` yourself.

4. **Scoping out the load-bearing bit**. "Not-a-goal" entries in a spec
   must be scrubbed against the user's real ask. Adding
   `"不实装 APScheduler 留给单独任务"` to PR-B1's Non-Goals directly
   contradicted the user's core need ("最快看到 AI 的回复"), which
   requires cycles running. Scope-cuts must not amputate the critical
   path.

5. **Declaring "done" without a user screenshot/demo**. If you cannot
   show a user-visible artifact (screenshot, curl output with real data,
   video), the work is not done. "Ready in theory" = "not ready".

6. **Changing code without updating all related documentation**. Every code
   change that affects behavior, architecture, APIs, or configuration MUST
   also update ALL related documentation — README (all language versions),
   CLAUDE.md project context section, inline docs, and any `.omc/` specs or
   plans. If a Chinese README exists alongside an English one, both must be
   updated. Documentation drift is a bug, not a nice-to-have.

---

## 📐 Project Context (quick reference)

Post-Agno-cutover state (2026-04-26). The migration spec's four
acceptance gates are all green; T1–T10 hardening shipped on top of it.
See `docs/AGNO_MIGRATION_TRACKER.md` for the full ledger.

- **Stack**: Python 3.11 (FastAPI + SQLAlchemy async + Agno 2.x +
  AgentOS + APScheduler) + Next.js 14 App Router + Tailwind + Recharts.
- **Agent runtime**: single Agno Agent (`agents/trading_agent.py`) +
  optional Team coordinate mode (`agents/experts_team.py`) for the two
  team-eligible strategies. Agno is the *only* LLM/agent/MCP framework
  — `rg "from langgraph|from langchain|import litellm|import mcp2py"
  apps/backend/src/` returns 0.
- **DB**: Postgres `pgvector/pgvector:pg16` (image swap landed in T10
  ops commit). Alembic 0001..0007 under `apps/backend/alembic/versions/`.
  AgentOS auto-creates `ai.*` tables (`agno_sessions`, `agno_runs`,
  `agno_traces`, `agno_spans`, `agno_knowledge`, `trade_journal`, ...)
  on first request. SQLite still works for unit tests via
  `aiosqlite` — migration `0007` is dialect-gated, no-op on SQLite.
- **LLM**: DeepSeek through Agno's `DeepSeek(id=...)` (no LiteLLM).
  `LLM_API_KEY` + `LLM_BASE_URL=https://api.deepseek.com/v1` +
  `AGNO_LLM_MODEL=deepseek-v4-pro` (or `-flash` / `-reasoner`).
  DeepSeek's API only serves chat — `/v1/embeddings` is unimplemented.
- **Embedder (T10)**: `EMBEDDER_PROVIDER=fastembed` is the default —
  CPU-bound `BAAI/bge-small-en-v1.5` (384-dim), no API key. The OpenAI
  protocol path stays available for operators on real OpenAI / proxies
  (`EMBEDDER_PROVIDER=openai` reuses `LLM_API_KEY`/`LLM_BASE_URL`).
  fastembed pulls the model from `HF_ENDPOINT=https://hf-mirror.com`
  (huggingface.co's TLS handshake is unreliable on cn networks).
- **Exchange**: Gate.io testnet via ccxt (`GATE_API_KEY` +
  `GATE_API_SECRET`); OKX adapter is the alternate.
- **Scheduler**: AgentOS native cron drives the trading-cycle Workflow
  (15s poll). APScheduler keeps the 6 fast position-protection
  monitors (`account_recorder` / `trailing_stop` / `stop_loss` /
  `partial_profit` / 10s cadence) where the AgentOS poller's interval
  is too coarse. `AGNO_SCHEDULER_DRIVES_CYCLE=true` + Postgres makes
  this the only path; APScheduler's old `trading_cycle` job is
  suppressed in that mode.
- **Manual cycle trigger**: `POST /api/v1/cycle/trigger` —
  `cycle_trigger_timeout_seconds` defaults 60s (bump to 180+ for
  reasoner / `-pro` since they routinely take 100–200s on the
  tribunal strategy).
- **Structured reasoning schema**: `StructuredReason` in
  `agents/tools/structured_reason.py` (7 fields: market_context,
  gates_passed, invalidation_condition, plan, confidence,
  justification, output_language). API surface: GET
  `/api/v1/decisions` serialises all of them plus `run_id` (T5+T6 —
  `correlation_id` was renamed; the only remaining `correlation_id`
  refs are the HTTP-request-trace ContextVar layer, intentional).
- **Decision tools (4)**: `open_position` / `close_position` /
  `partial_close` / `hold_tool` in `agents/tools/decision_schemas.py`.
  T9 wraps `open_position` with `requires_confirmation` so opens with
  USD notional > `hitl_open_size_threshold_usd` (default 10000) pause
  for operator approval via `EVENT_RUN_PAUSED` SSE +
  `POST /api/v1/runs/{id}/{confirm,reject}` + dashboard
  `ApprovalBanner.tsx`.
- **MCP tools (15)**: 9 exchange/account in
  `infrastructure/mcp/trading_mcp_server.py` + 6 crypto-data in
  `infrastructure/data_sources/crypto_mcp_server.py`. Loaded via
  Agno's `MultiMCPTools` (formerly mcp2py — fully removed).
- **Knowledge / RAG (T10)**: every cycle's `StructuredReason` is
  serialised → ingested as a knowledge document into
  `ai.trade_journal` (PgVector hybrid search). On the next cycle the
  Agno Agent has `search_knowledge=True` and auto-injects the most
  semantically relevant prior decisions into the system prompt. Hook
  fires post-`decision_service.record` from
  `application/monitors/trading_loop_monitor.py::_schedule_journal_ingest`
  via `asyncio.create_task` (never blocks the cycle return).
- **Tracing (T4)**: `observability/tracing.py::setup_tracing` calls
  `agno.tracing.setup_tracing(db=PostgresDb)` in lifespan (idempotent;
  killed by `OTEL_TRACING_ENABLED=false`). OpenInference's
  `AgnoInstrumentor` emits one OTel span per Agent.arun / model call /
  tool call. `GET /traces` (AgentOS) returns the per-cycle span tree.
- **G5 guardrail (T3)**: `agents/guardrails/qa_phrase.py` post_hook
  scans `RunOutput.content` for the 11 fault phrases; matches publish
  `EVENT_ORCHESTRATOR_ERROR` so the dashboard banner auto-lights.
- **Session memory (T2)**: `enable_session_summaries=True` +
  `add_history_to_context=True` + `num_history_runs=5`. Persisted to
  `ai.agno_sessions.summary` per `_TRADING_SESSION_ID =
  "omnitrade-trading"`.
- **13 prompts**: single-source English, Alpha Arena 4-section
  (IDENTITY / QUANTITATIVE FRAMEWORK / VALIDATION GATES / OUTPUT
  SPECIFICATION). `OUTPUT_LANGUAGE` controls reply language.
- **11 strategies**: each defined in `domain/enums.py::StrategyName`.
  `arena-tribunal` and `arena-raider-squad` are the team-eligible
  pair; the other 9 run as a single Agno Agent. Spec Acceptance 3
  (every strategy completes a cycle) is enforced by
  `tests/agents/test_strategies_acceptance3.py` (12 deterministic
  tests, no LLM).
- **Frontend**: SSE single transport (WS removed). Dashboard at
  `http://localhost:3000/dashboard` — `AgentReasoningFeed.tsx`
  (5-panel structured) + `ApprovalBanner.tsx` (T9 HITL) +
  `LogStream.tsx` + i18n via `apps/frontend/lib/i18n/`. Reads from
  `useRealtime` hook over `/sse/*`.
- **Backtest**: `backtest/engine.py` + `backtest/agno_think.py`
  (injected `ThinkFn`; no MCP / no DB) + `backtest/cassette.py`
  (vcrpy HTTP-layer record/replay; `--cassette / --cassette-mode`
  CLI flags).
- **Eval**: T7 ReliabilityEval (`tests/eval/test_reliability_cycle.py`)
  + T8 AccuracyEval (`tests/eval/test_accuracy_g2.py`) — both run in
  the dedicated `Agent ReliabilityEval (Agno)` CI step under
  `pytest -m eval`.

## 🧭 Working directories / key files

```
apps/backend/src/omnitrade/
  agents/
    trading_agent.py              — build_agno_think_fn (Agno Agent + MultiMCPTools
                                     + DecisionRecorder + post_hooks + HITL pause loop
                                     + Knowledge handle)
    experts_team.py               — Agno Team (coordinate mode) for the two
                                     team-eligible strategies
    hitl.py                       — should_require_confirmation() predicate +
                                     ApprovalRegistry (asyncio.Future store) (T9)
    guardrails/qa_phrase.py       — G5 fault-phrase post_hook (T3)
    knowledge/trade_journal.py    — Knowledge factory + serialiser + ingest (T10)
    prompts/                      — 13 prompt files (system / think / reflect +
                                     7 experts + multi_agent variants)
    tools/
      decision_schemas.py         — 4 decision tools + wrap_open_position_for_hitl
      mcp_bridge.py               — AgnoMCPBridge / MultiMCPTools wiring
      structured_reason.py        — StructuredReason pydantic + DB column mapping
  application/
    composition.py                — build_trading_monitor (THE wire-everything fn)
    trading_workflow.py           — Agno Workflow registered with AgentOS
    monitors/
      trading_loop_monitor.py     — scheduler tick wrapper + post-cycle ingest hook
      trailing_stop_monitor.py    — } the 6 fast position-protection monitors
      stop_loss_monitor.py        —   (10s cadence on APScheduler)
      partial_profit_monitor.py   — } three-way state UPDATE happens here
      account_recorder_monitor.py
      ...
    decision_service.py           — persists Decision row → run_id
    risk_service.py               — DailyLossLimiter
    events/bus.py                 — EVENT_RUN_PAUSED / ORCHESTRATOR_ERROR / ...
  api/
    main.py                       — lifespan: configure_structlog → setup_tracing
                                     → ApiContainer → AgentOS overlay → schedules
    agent_os_app.py               — wrap_with_agent_os (FastAPI + AgentOS overlay,
                                     +88 AgentOS routes)
    routes/
      cycle.py                    — POST /api/v1/cycle/trigger
      decisions.py                — GET /api/v1/decisions (with run_id, all 7
                                     StructuredReason fields)
      runs.py                     — POST /api/v1/runs/{id}/{confirm,reject} (T9)
      positions.py / account.py / prices.py / ...
    sse/stream.py                 — EVENT_* fan-out SSE
  infrastructure/
    llm/agno_llm_adapter.py       — the only LLMClient (Agno's DeepSeek)
    mcp/trading_mcp_server.py     — 9 trading tools (FastMCP stdio)
    data_sources/crypto_mcp_server.py  — 6 crypto-data tools
    exchange/ccxt_exchange.py     — Gate/OKX adapter (phantom-positions fix in
                                     fetch_positions: use `contracts` only, never
                                     `contractSize`)
    persistence/
      database.py                 — psycopg3 routing (single driver sync+async)
      models.py                   — ORM (`agent_decisions.run_id` post T5+T6)
      repositories/
    scheduling/scheduler.py       — APScheduler for the 6 fast monitors only
    market_data/indicators.py     — EMA / RSI / MACD / ATR / volume_ratio
  observability/
    tracing.py                    — setup_tracing (T4 OTel overlay, idempotent)
    trace_context.py              — HTTP-request `correlation_id` ContextVar
                                     (orthogonal to OTel; do NOT rename — it's
                                     not the per-cycle run_id)
  backtest/
    engine.py                     — injected ThinkFn, no MCP / no DB
    agno_think.py                 — Agno Agent → think_fn factory for CLI runs
    cassette.py                   — vcrpy HTTP record/replay
  config.py                       — Settings (pydantic-settings) — all knobs
  main.py                         — entry point

apps/frontend/
  app/dashboard/page.tsx          — Console layout
  components/
    AgentReasoningFeed.tsx        — 5-panel structured + blockquote fallback
    ApprovalBanner.tsx            — T9 HITL approve/reject UI
    LogStream.tsx                 — SSE-driven log feed
    reasoning/                    — 5 panel components (MarketContext / Gates /
                                     Invalidation / Plan / ConfidenceGauge)
  lib/
    sse/{client,singleton}.ts     — SSE single transport (WS deleted)
    api/{client,types}.ts         — API DTOs (run_id, paused-run payload, ...)
    i18n/{messages.ts,context.tsx}— zh/en lightweight i18n
  hooks/useRealtime.ts            — single source of truth for live state

docs/
  AGNO_MIGRATION_TRACKER.md       — current ledger (T1–T10, A1–A4)
  ARCHITECTURE.md / ARCHITECTURE_ZH.md  — DDD layers + scheduler topology +
                                          three-way state invariant

.omc/
  specs/                          — deep-interview output
  plans/                          — ralplan consensus output
  autopilot/                      — phase reports + probe logs
```

## 🏷 Git commit style

- Conventional commits with scope: `feat(backend):`, `fix(frontend):`,
  `chore(backend):`, `test:`
- Include `Co-Authored-By: Claude ...` footer on AI-assisted commits
- First line ≤ 70 chars
- Body explains WHY more than WHAT (the diff shows what)

## 🤝 User working style (from repeated signals)

- Prefers Chinese for conversation + option labels
- Accepts fast iteration with rollback over slow-but-safe defaults
- Values honest post-mortems over defensive framing
- Trusts concrete verification (screenshots, real curl output) over
  promises
- Will push back sharply when work isn't truly complete — trust this
  signal, don't paper over
