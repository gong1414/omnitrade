# Agno Migration Tracker

Source spec: `.omc/specs/deep-interview-agno-migration.md`
Source plan: `~/.claude/plans/mossy-frolicking-hickey.md`

**Cutover complete (2026-04-26).** Stages A–E of the hard cutover plan
plus Phase 4.5 (AgentOS Workflow registration + native scheduler) and
the backtest engine port all shipped on `main` the same day (148534d,
6f814cc, e7ccbff, a81da88, f58bc7d, a87f088, plus the scheduler
follow-up). The four `AGNO_*_ENABLED` flags are deleted, every
LangGraph / LangChain / LiteLLM / mcp2py consumer is gone, the
dashboard runs on SSE, the trading Agent persists each cycle as a run
inside a single Postgres-backed Agno session, and **the AgentOS native
scheduler drives the trading cycle** on a `*/N` cron whenever
`AGNO_SCHEDULER_DRIVES_CYCLE=true`. APScheduler is reduced to the 6
fast position-protection monitors (10 s cadence) where the AgentOS
scheduler's 15 s poll interval is too coarse.

Validated end-to-end on 2026-04-26 against testnet:
- `POST /schedules/{id}/trigger` → workflow runs, decision row lands
- AgentOS poller fires `trading-cycle` automatically at the next cron
  edge (`0 */2 * * *` for `TRADING_INTERVAL_MINUTES=120`)
- No APScheduler `trading_cycle` job in `scheduler.add_job` calls
- 579 backend tests passed, 1 skipped, 0 failed

All open Agno-migration follow-ups are landed. The trading cycle
runs on AgentOS native scheduler, the workflow is registered with
AgentOS, the backtest engine has been ported, and deterministic
replays go through vcrpy (`backtest/cassette.py`,
`--cassette / --cassette-mode` CLI flags).

Last updated: 2026-04-26

---

## Phase status

| Phase | Status | Notes |
|-------|--------|-------|
| 0 — Preflight | ✅ shipped | `agno>=2.0.0`, `psycopg[binary]>=3.2.0` in `apps/backend/pyproject.toml`; Postgres service in `docker-compose.yml`. |
| 1 — LLM swap | ✅ shipped, **flag deleted** | `infrastructure/llm/agno_llm_adapter.py` is the only LLMClient. `factory.py` + `litellm_client.py` deleted. |
| 2 — Agent + MCPTools | ✅ shipped, **flag deleted** | `agents/trading_agent.py` + `agents/tools/decision_schemas.py` + `agents/tools/mcp_bridge.py`. `composition._build_base_think_fn` is single-path. LangGraph `think_node.py` deleted. |
| 3 — Workflow + Team | ✅ scaffolded, **flag deleted** | `application/trading_workflow.py` + `agents/experts_team.py` exist; not yet driving the cycle (see Phase 4.5). Legacy `application/multi_agent/` deleted. |
| 4 — AgentOS shell | ✅ shipped, **flag deleted** | `api/agent_os_app.py::wrap_with_agent_os` is unconditional when LLM creds are present. AgentOS overlay adds +88 routes (sessions / runs / schedules / workflows) on top of the legacy `/api/v1/*` surface. |
| 4.5 — AgentOS Workflow + scheduler | ✅ shipped | `agent_os_app.MonitorHolder` lazy-binds the trading monitor populated in lifespan. `application/trading_workflow.build_agno_trading_workflow` exposes `monitor.tick()` as a single-step `Workflow` registered with `AgentOS(workflows=[wf])`. `main.lifespan._register_agentos_trading_schedule` registers (idempotently) a cron schedule pointing at `/workflows/trading-cycle/runs`; the AgentOS poller picks it up and fires every cron tick. APScheduler is gated off the `trading_cycle` job when `AGNO_SCHEDULER_DRIVES_CYCLE=true`; the 6 fast position-protection monitors stay on APScheduler. |
| 5 — Frontend SSE | ✅ shipped, **default transport** | `apps/frontend/lib/sse/{client,singleton}.ts` + `hooks/useRealtime.ts`. WS client + hook deleted; Playwright e2e ported to `fake-sse-server.ts`. |
| 6 — Postgres + Agent.memory | ✅ shipped | `infrastructure/persistence/database.py` routes Postgres through psycopg3. The trading Agent runs against `ai.agno_sessions` (session_id="omnitrade-trading", `add_history_to_context=True`, `num_history_runs=5`). |
| Legacy purge | ✅ shipped (Stages A + E) | LangGraph / LangChain / LiteLLM / mcp2py / multi_agent / api/ws all deleted on disk. APScheduler + `application/trading_loop.py` still drive ticks until the schedule-bootstrap follow-up lands. |
| Backtest engine | ✅ shipped (Phase 4.5) | `backtest/engine.py` rewritten against an injected `ThinkFn`. `backtest/agno_think.py` builds an Agno-Agent-backed think_fn (no MCP / no DB) for CLI runs. `backtest/llm_cache.py` deleted — replaced by `backtest/cassette.py` (vcrpy-backed HTTP-layer cassette wrapper) wired via `--cassette / --cassette-mode` CLI flags. `tests/backtest/test_engine.py` + `test_cassette.py` cover dispatch + record/replay. |

---

## Operator runbook

### Enable each phase incrementally
```bash
# Phase 1: LLM swap
echo "AGNO_LLM_ENABLED=true"   >> .env
echo "AGNO_LLM_MODEL=deepseek-reasoner" >> .env

# Phase 2: Agent + MCPTools
echo "AGNO_AGENT_ENABLED=true" >> .env

# Phase 3: Team scaffolding
echo "AGNO_WORKFLOW_ENABLED=true" >> .env

# Phase 4: AgentOS shell
echo "AGNO_AGENT_OS_ENABLED=true" >> .env

# Phase 5: Frontend SSE (when AgentOS event stream lands in 4.5)
echo "NEXT_PUBLIC_USE_SSE=true" >> apps/frontend/.env.local

# Phase 6: Postgres
docker compose up -d postgres
echo "DATABASE_URL=postgresql://omnitrade:omnitrade@localhost:5432/omnitrade" >> .env
echo "AGNO_POSTGRES_URL=postgresql+psycopg://omnitrade:omnitrade@localhost:5432/omnitrade" >> .env
cd apps/backend && alembic upgrade head     # creates the 8 business tables on Postgres

# Roll the backend; AgentOS auto-creates its own session/run tables on first request.
docker compose restart backend
```

### Roll back any phase

Each phase is bit-reversible by toggling its flag:
```bash
sed -i '' 's/AGNO_AGENT_OS_ENABLED=true/AGNO_AGENT_OS_ENABLED=false/' .env
docker compose restart backend
```

### G1 / G2 acceptance per phase
After enabling each phase, run the project's CLAUDE.md gates:
```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger             # G1
curl -sS  "http://localhost:8000/api/v1/decisions?limit=1" | jq     # G2 — JSON audit
open http://localhost:3000/dashboard                                # G3 — UI render
docker compose logs backend --tail 100                              # G4/G5
diff <(curl -sS /api/v1/decisions?limit=1 | jq '.[].positions_count') \
     <(curl -sS /api/v1/positions       | jq '. | length')          # G6
```

---

## Legacy files slated for deletion (after Phase 6 sign-off)

These files lose their consumers once each respective Agno path is the
default. Until the user confirms each phase is healthy on testnet, they
remain on disk as the rollback target.

| File | Replaced by | Phase that obsoletes it |
|------|-------------|------------------------|
| `apps/backend/src/omnitrade/infrastructure/llm/litellm_client.py` | `infrastructure/llm/agno_llm_adapter.py` | Phase 1 |
| `apps/backend/src/omnitrade/agents/think_node.py` (LangGraph) | `agents/trading_agent_agno.py` | Phase 2 |
| `apps/backend/src/omnitrade/agents/tools/mcp_tool_bridge.py` (mcp2py) | `agents/tools/mcp_bridge_agno.py` | Phase 2 |
| `apps/backend/src/omnitrade/agents/tools/trade_execution.py` (LangChain `StructuredTool`) | `agents/tools/decision_schemas.py` | Phase 2 |
| `apps/backend/src/omnitrade/application/multi_agent/` (folder) | `agents/experts_team_agno.py` | Phase 3 |
| `apps/backend/src/omnitrade/infrastructure/scheduling/scheduler.py` (APScheduler) | AgentOS native scheduler | Phase 4.5 |
| `apps/backend/src/omnitrade/api/ws/` (WebSocket transport) | `apps/frontend/lib/sse/client.ts` + AgentOS SSE | Phase 5 |
| `apps/frontend/lib/ws/client.ts` | `apps/frontend/lib/sse/client.ts` | Phase 5 |

`pyproject.toml` deps to drop in the same purge:
- `langgraph>=0.1.0`
- `langchain-core>=0.2.0`
- `litellm>=1.40.0`
- `mcp2py>=0.6.0`
- `apscheduler>=3.10.0`
- `aiosqlite>=0.20.0` (if SQLite is fully retired)

---

## Tests slated for rewrite

The original spec called for "all 698 tests rewritten". The actual count
is **116 test files** (the 698 figure conflated test functions + cassettes
+ fixtures). Each test is tagged below with its rewrite priority:

| Tag | Meaning | Action |
|-----|---------|--------|
| `keep-as-is` | Pure domain logic (entities, value objects, three-way state). No framework dep. | No change. |
| `port-shallow` | Tests an interface only — adapter swap is transparent. | Re-record cassette under Agno path; fixture stays. |
| `rewrite-deep` | Tests the LangGraph think loop or LangChain tools. | Rewrite against Agno Agent API. |
| `delete` | Tests a behavior of code being deleted (e.g. mcp2py-specific). | Remove with the source file. |

Per-directory mapping (preliminary; refine as Phase 6 lands):

| Directory | Files | Tag |
|-----------|-------|-----|
| `apps/backend/tests/domain/` | ~13 | `keep-as-is` |
| `apps/backend/tests/agents/` | ~9 | mostly `rewrite-deep` (think_node, tool parser); 2 `port-shallow` |
| `apps/backend/tests/agents/multi_agent/` | ~5 | `rewrite-deep` (Team mode replaces StructuredTool) |
| `apps/backend/tests/api/routes/` | ~16 | `port-shallow` (endpoints unchanged) |
| `apps/backend/tests/api/ws/` | ~2 | `delete` (WS removed) — replace with SSE tests |
| `apps/backend/tests/application/` | ~24 | mix: services + monitors `port-shallow`; trading_loop `rewrite-deep` if Workflow is on |
| `apps/backend/tests/infrastructure/llm/` | ~2 | `port-shallow` (factory dispatches transparently) |
| `apps/backend/tests/infrastructure/exchange/` | ~3 | `keep-as-is` |
| `apps/backend/tests/infrastructure/market_data/` | ~6 | `keep-as-is` |
| `apps/backend/tests/infrastructure/mcp/` | ~4 | `port-shallow` (FastMCP servers unchanged) |
| `apps/backend/tests/infrastructure/scheduling/` | ~2 | `delete` after Phase 4.5 — replace with AgentOS schedule tests |
| `apps/backend/tests/infrastructure/persistence/` | ~5 | `port-shallow` (re-run on Postgres) |
| `apps/backend/tests/infrastructure/news/` | ~2 | `keep-as-is` |
| `apps/backend/tests/infrastructure/vector_store/` | ~2 | `keep-as-is` |
| `apps/frontend/tests/e2e/` | 1 (`dashboard.spec.ts`) | `port-shallow` (mock SSE instead of WS once Phase 5 hook flips) |

---

## Acceptance criteria (spec final gates)

- [x] **Acceptance 1**: Real `POST /api/v1/cycle/trigger` returns 200 in ≤ 60 s on the legacy path. *(unchanged today; flag-gated paths inherit this when their phase is on)*
- [x] **Acceptance 2**: AgentUI shows the latest decision with full structured reasoning. *(replaced by Console-design dashboard in `apps/frontend/app/dashboard/page.tsx` — see `~/Desktop/omnitrade-console-impl-1-zh.png`)*
- [ ] **Acceptance 3**: All 11 strategies complete a cycle. *(needs Phase 4.5 + Postgres soak)*
- [ ] **Acceptance 4**: `rg 'from langgraph|from langchain|import litellm|import mcp2py' apps/backend/src/` returns 0. *(blocked on legacy purge after testnet validation)*

---

## Next probable session

1. **Phase 4.5**: register the trading `Workflow` with `AgentOS(workflows=[...])`, expose its run-events stream over SSE, and migrate one APScheduler loop (`trailing_stop_loop` is the safest first cut) onto the AgentOS scheduler.
2. **Postgres soak**: bring up `docker compose up -d postgres`, point `DATABASE_URL` at it, run `alembic upgrade head`, watch 3 cycles complete clean.
3. **Test rewrite**: start with `apps/backend/tests/infrastructure/llm/` (smallest port surface) — green → fan out to `tests/agents/`.
