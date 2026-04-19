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

---

## 📐 Project Context (quick reference)

- **Stack**: Python 3.11 (FastAPI + SQLAlchemy async + APScheduler) +
  Next.js 14 App Router + Tailwind + Recharts
- **DB**: SQLite at `data/omnitrade.db` (migrations under
  `apps/backend/alembic/versions/`)
- **LLM**: DeepSeek V3.2 via LiteLLM (`settings.llm_model_name =
  "deepseek/deepseek-chat"`); API key in `LLM_API_KEY` env var at repo
  root `.env`
- **Exchange**: Gate.io testnet (via ccxt); creds `GATE_API_KEY` +
  `GATE_API_SECRET`; testnet flag default True
- **Scheduler**: `SCHEDULER_ENABLED=true` + `TRADING_INTERVAL_MINUTES`
  control cadence. Default OFF in `.env.example` (safety); enabled in
  local `.env`.
- **Manual cycle trigger**: `POST /api/v1/cycle/trigger` (60s timeout,
  asyncio.Lock prevents concurrent triggers)
- **Structured reasoning schema**: `StructuredReason` in
  `agents/tools/structured_reason.py` — 7 fields (market_context /
  gates_passed / invalidation_condition / plan / confidence /
  justification / output_language)
- **13 prompts**: all single-source English, Alpha Arena 4-section
  structure (IDENTITY / QUANTITATIVE FRAMEWORK / VALIDATION GATES /
  OUTPUT SPECIFICATION). `OUTPUT_LANGUAGE` runtime param controls which
  language the LLM replies in.
- **Dashboard**: http://localhost:3000/dashboard — AgentReasoningFeed
  renders structured 5-panel when new fields present, blockquote
  fallback for legacy rows

## 🧭 Working directories / key files

```
apps/backend/src/omnitrade/
  agents/
    prompts/            — 13 prompt files (system/think/reflect + 7 experts)
    tools/
      structured_reason.py  — StructuredReason schema (DB column mapping at bottom)
      trade_execution.py    — 4 LLM tools (open/close/partial/hold)
    think_node.py       — LangGraph compile + dual-path parser
  application/
    composition.py      — build_trading_monitor (THE wire-it-all-together fn)
    trading_loop.py     — 6-step cycle orchestrator (observe→news→think→risk→execute→reflect)
    monitors/
      trading_loop_monitor.py  — scheduler tick wrapper
  api/
    main.py             — lifespan with APScheduler start/stop
    routes/
      cycle.py          — POST /api/v1/cycle/trigger
      decisions.py      — GET /api/v1/decisions (serialize all 6 structured cols)
  infrastructure/
    exchange/
      ccxt_exchange.py  — Gate/OKX adapter; phantom-positions bug fixed
                          (line 142-147: use `contracts` only, not
                          `contractSize` — per this file's CRITICAL rule)

apps/frontend/
  components/
    AgentReasoningFeed.tsx        — conditional 5-panel vs legacy blockquote
    reasoning/                     — 5 panel components
  lib/
    i18n/{messages.ts,context.tsx} — zh/en lightweight i18n

.omc/
  specs/                — deep-interview output (acceptance criteria source)
  plans/                — ralplan consensus output
  autopilot/            — phase reports + probe logs
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
