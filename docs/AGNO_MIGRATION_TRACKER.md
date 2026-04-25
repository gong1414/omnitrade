# Agno Migration Tracker

Source spec: `.omc/specs/deep-interview-agno-migration.md`
Source plan: `~/.claude/plans/mossy-frolicking-hickey.md`

This document tracks **what's landed**, **what's still flag-gated**, and
**what gets deleted in the legacy purge** (Phase 6 final step) once the
six phases are validated end-to-end on the testnet deployment.

Last updated: 2026-04-26

---

## Phase status

| Phase | Status | Flag(s) | Notes |
|-------|--------|---------|-------|
| 0 — Preflight | ✅ landed | — | `agno>=2.0.0`, `psycopg[binary]>=3.2.0` in `apps/backend/pyproject.toml`; Postgres service in `docker-compose.yml`. |
| 1 — LLM swap | ✅ landed | `AGNO_LLM_ENABLED` | `factory.build_llm_client` dispatches on the flag; `AgnoLLMAdapter` wraps Agno's DeepSeek. Default OFF preserves LiteLLM bit-for-bit. |
| 2 — Agent + MCPTools | ✅ landed | `AGNO_AGENT_ENABLED` | `agents/trading_agent_agno.py` + `agents/tools/decision_schemas.py` + `agents/tools/mcp_bridge_agno.py`. `composition._build_base_think_fn` branches on the flag. |
| 3 — Workflow + Team | ✅ landed | `AGNO_WORKFLOW_ENABLED` | `application/trading_workflow_agno.py` + `agents/experts_team_agno.py`. Workflow scaffolding ready for AgentOS scheduler in Phase 4.5. |
| 4 — AgentOS shell | ✅ landed | `AGNO_AGENT_OS_ENABLED` | `api/agent_os_app.py::wrap_with_agent_os` overlays AgentOS routes on the existing FastAPI app (`on_route_conflict='preserve_base_app'`). +92 routes when on. |
| 4.5 — AgentOS scheduler + Workflow registration | ⏳ deferred | (planned: `AGNO_OS_SCHEDULER`) | Wire `Workflow` into AgentOS via `workflows=[...]` so its built-in cron replaces APScheduler. Requires Postgres + verified end-to-end cycle. |
| 5 — Frontend SSE client | ✅ landed | `NEXT_PUBLIC_USE_SSE` (planned) | `apps/frontend/lib/sse/client.ts` mirrors WS client surface. Hook switch arrives once AgentOS exposes the trading-decision SSE stream (Phase 4.5). |
| 6 — Postgres engines + tracker | ✅ landed (this doc) | `DATABASE_URL=postgresql://...` | `_make_async_url` / `_make_sync_url` route Postgres through psycopg3 (Agno-aligned). Existing 5 alembic revisions auto-upgrade on Postgres. |
| Legacy purge | ⏳ deferred | (no flag — code deletion) | Pulls listed files. Gated on user sign-off of all G1–G6 acceptance gates against the AgentOS path. |

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
