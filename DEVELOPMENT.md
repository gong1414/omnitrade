# Development guide

> English · [简体中文](DEVELOPMENT_ZH.md)

This is the deep-dive setup guide for working on OmniTrade itself.
Reading order:

1. [README.md](README.md) — what the project is and how to run it as a user.
2. [CONTRIBUTING.md](CONTRIBUTING.md) — the contract: hard rules, PR
   checklist, commit style.
3. **DEVELOPMENT.md** (this file) — the inner loop: how to run / debug /
   profile / extend each layer.
4. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the why behind the
   layers.

If you only want to run the system, [docs/QUICKSTART.md](docs/QUICKSTART.md)
gets you to a first cycle in 5 minutes.

## 1. Local environments

### Path A — Docker (matches CI most closely)

```bash
cp apps/backend/.env.example .env
docker compose up -d
docker compose logs backend -f
```

Pros: postgres + pgvector + db-init + backend + frontend all wired.
Cons: ~3 min first-boot for image build + `BAAI/bge-small-en-v1.5`
download, attaching a debugger requires extra work.

### Path B — Local Python + Node (fastest inner loop)

```bash
# Backend (in one terminal)
cd apps/backend
uv sync --all-extras
uv run alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./data/dev.db \
  uv run uvicorn omnitrade.api.app:create_app --factory --reload --port 8000

# Frontend (in another terminal)
cd apps/frontend
npm install
npm run dev   # http://localhost:3000
```

Pros: instant restart, `pdb` works, easier IDE integration.
Cons: SQLite-only (no pgvector); the T10 RAG layer is a no-op against
SQLite — that's intentional, but you don't see Knowledge ingestion.

### Path C — hybrid (Postgres in Docker + backend on host)

```bash
docker compose up -d postgres                                       # only PG + pgvector
DATABASE_URL=postgresql+psycopg://omnitrade:omnitrade@localhost:5432/omnitrade \
  uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://omnitrade:omnitrade@localhost:5432/omnitrade \
  uv run uvicorn omnitrade.api.app:create_app --factory --reload
```

Best for working on T10 RAG / migrations / pgvector queries while still
keeping a fast local Python iteration loop.

## 2. Inner loop

### Backend tests

```bash
cd apps/backend
uv run pytest -m "not manual_qa"                            # CI-safe (~25 s)
uv run pytest tests/agents/                                 # agent layer only
uv run pytest -m eval                                       # T7 ReliabilityEval + T8 AccuracyEval
uv run pytest -m manual_qa                                  # live LLM (needs LLM_API_KEY)
uv run pytest tests/agents/test_strategies_acceptance3.py   # 11 strategies × cycle
uv run pytest tests/behavioral_equivalence/                 # 22-fixture replay
```

Coverage:

```bash
uv run pytest --cov=src/omnitrade --cov-report=html
open htmlcov/index.html
```

### Backend linters / type-checker

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy --strict src/
```

CI runs all three; PRs must pass them. Local pre-commit hook runs the
same — install with:

```bash
uv tool install pre-commit
pre-commit install
```

### Frontend tests

```bash
cd apps/frontend
npm run lint
npm run type-check
npm run test                       # vitest
npm run test:e2e                   # Playwright (needs a running backend)
```

### Single-cycle smoke

The fastest "did I break anything end-to-end?" check is to trigger one
cycle and read its decision JSON:

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq
```

This is also how you should walk the [G1–G6 acceptance gates](CLAUDE.md)
before declaring a PR done.

## 3. Database

### Migrations

```bash
uv run alembic upgrade head                  # apply all
uv run alembic downgrade -1                  # revert one
uv run alembic history                       # list revisions
uv run alembic revision -m "your change"     # author a new revision
```

Revisions live in `apps/backend/alembic/versions/`. The most recent are
documented in [`apps/backend/README.md`](apps/backend/README.md).

When you add a new migration, you MUST verify both upgrade AND
downgrade (round-trip):

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

If `downgrade()` doesn't exist or breaks, document why in the migration
docstring.

### Inspecting the DB

```bash
docker compose exec postgres psql -U omnitrade -d omnitrade
\dt ai.*
\d agent_decisions
SELECT id, run_id, action, structured_confidence FROM agent_decisions ORDER BY id DESC LIMIT 5;
```

For SQLite (Path B):

```bash
sqlite3 apps/backend/data/dev.db
.tables
.schema agent_decisions
```

## 4. Adding things

### A new strategy

1. Add a member to `domain/enums.py::StrategyName`
2. Drop a prompt file in `agents/prompts/`
3. Wire the strategy into `agents/trading_agent.py::build_agno_think_fn`'s
   selector
4. Add a row to `tests/agents/test_strategies_acceptance3.py` — every
   strategy must complete a cycle deterministically (no LLM calls)
5. Update `docs/STRATEGIES.md`
6. Re-run the 22 frozen-fixture gate; ≥ 0.95 must hold

### A new MCP tool

1. Add a function to one of the FastMCP servers under
   `infrastructure/mcp/` or `infrastructure/data_sources/`
2. The tool is auto-discovered by `MultiMCPTools` via stdio
3. Test it with a `manual_qa`-marked test under `tests/agents/`
4. Update [`docs/TOOL_INVENTORY.md`](docs/TOOL_INVENTORY.md)

### A new dashboard panel

1. Add a React component under `apps/frontend/components/`
2. Wire it via the `useRealtime` hook (single SSE source of truth)
3. Add a vitest snapshot test under `components/__tests__/`
4. Update the screenshot in `assets/` (manual)

### A new env var

1. Add the field to `apps/backend/src/omnitrade/config.py::Settings`
2. Add the row to `apps/backend/.env.example` AND to root `.env.example`
   with a documenting comment
3. If user-facing, add a row to the `🧠 Environment` table in
   [README.md](README.md) and [README_ZH.md](README_ZH.md)
4. The PR template's checklist will remind you of these on submit

## 5. Debugging recipes

### "AI is hallucinating positions"

```bash
curl -s http://localhost:8000/api/v1/positions | jq
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq '.positions_count'
# These two must agree. Disagreement = G6 cross-source bug.
```

The `infrastructure/exchange/ccxt_exchange.py::fetch_positions` reads
`contracts` only, never `contractSize` — that's the historical fix.

### "Cycle hangs / takes forever"

```bash
docker compose logs backend --tail 200 | grep -i 'mcp\|timeout\|429\|rate'
# Common causes:
#   - LLM provider rate-limited (HTTP 429)
#   - reasoner model genuinely slow (bump cycle_trigger_timeout_seconds)
#   - one MCP server timed out (the other 14 still work)
```

### "Where's the per-cycle trace?"

```bash
curl -s http://localhost:8000/traces | jq
# AgentOS-served. Each entry is one Agno run with the full span tree
# under it (model calls, tool calls, hooks).
```

### "G5 fault phrase fired"

The agent's `market_context` / `gates_passed` / `justification`
contains one of 11 known failure phrases. Don't dismiss; investigate.
The exact phrases are listed in `agents/guardrails/qa_phrase.py`.

## 6. Performance

The default trading cycle (single-agent, `deepseek-v4-flash`, 2
symbols) runs in ~30–60 s wall time. The `arena-tribunal` strategy
with `deepseek-reasoner` can take 100–200 s.

If you need to speed up:

- Switch `AGNO_LLM_MODEL` to `deepseek-v4-flash` (cheapest + fastest)
- Disable team advisory (`MULTI_AGENT_ENABLED=false`)
- Trim `TRADING_SYMBOLS` to the symbols you actually want signals on
- Drop `ACCOUNT_RECORD_INTERVAL_MINUTES` only if you don't care about
  equity-curve granularity

### Profiling a cycle

```bash
uv run python -c "
import asyncio, cProfile, pstats
from omnitrade.application.composition import build_trading_monitor
async def main():
    mon = await build_trading_monitor(...)  # see tests/ for fixtures
    cProfile.runctx('asyncio.run(mon.tick())', globals(), locals(), 'cycle.prof')
asyncio.run(main())
"
uv run python -m pstats cycle.prof << 'EOF'
sort cumulative
stats 30
EOF
```

## 7. Release workflow

1. CI on `main` is green
2. Update `CHANGELOG.md` — move `Unreleased` items to a new versioned
   section
3. Tag locally: `git tag v0.x.0 -m "release notes"`
4. Push: `git push origin v0.x.0`
5. Create a GitHub release (`gh release create v0.x.0 --notes-from-tag`
   or paste from `CHANGELOG.md`)
6. Update the `📰 News` section at the top of both READMEs

## 8. Where to ask

- **Bug** → [issue with bug template](https://github.com/gong1414/omnitrade/issues/new?template=bug_report.md)
- **Feature** → [issue with feature template](https://github.com/gong1414/omnitrade/issues/new?template=feature_request.md)
- **Architecture / design discussion** → [Discussions](https://github.com/gong1414/omnitrade/discussions)
- **Security** → [SECURITY.md](SECURITY.md) (private channel — never an issue)
