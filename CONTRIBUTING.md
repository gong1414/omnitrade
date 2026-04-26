# Contributing to OmniTrade

> English · [简体中文](CONTRIBUTING_ZH.md)

Thanks for thinking about contributing. This is an LLM-driven crypto-futures
trading project — getting it wrong can cost real money on mainnet, so we
hold the bar high on testing, observability, and reproducibility. Read this
file end-to-end before sending a PR.

> 🛠 If you want the **deep-dive setup + debugging recipes** (multiple
> dev paths, profiling, debugging recipes, release workflow), see
> [DEVELOPMENT.md](DEVELOPMENT.md). This file is the contract; that file
> is the inner loop.

## TL;DR

```bash
# Backend
cd apps/backend
uv sync --all-extras
uv run pytest -m "not manual_qa"          # must be green
uv run ruff check .                        # must be clean

# Frontend
cd apps/frontend
npm ci
npm run lint                               # must be clean
npm run test                               # vitest

# Full stack (Postgres + pgvector + AgentOS scheduler)
cp .env.example .env                       # fill in secrets — git-ignored
docker compose up -d
curl -X POST http://localhost:8000/api/v1/cycle/trigger
```

## Hard rules (these earned themselves through real incidents)

These live in `CLAUDE.md` for AI collaborators; they apply equally to humans.

1. **No legacy frameworks.** This project runs on Agno only:
   ```bash
   rg "from langgraph|from langchain|import litellm|import mcp2py" apps/backend/src/
   ```
   must return zero hits. Any PR that re-introduces these gets rejected
   on sight.

2. **Walk the user-visible acceptance gates** (G1–G6 in `CLAUDE.md`)
   before claiming "done". `pytest PASS` is necessary but not sufficient
   — we got burned shipping technically-green changes that the user
   couldn't actually use.

3. **Three-way state atomicity.** Any code path that writes
   `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` MUST
   go through `PositionRepository.apply_three_way_state`.

4. **22/22 frozen-fixture replay.** Behavior-equivalence cassettes under
   `apps/backend/tests/behavioral_equivalence/` must replay clean. If
   you intentionally change agent behavior, re-record the cassette and
   call out the diff in your PR description.

5. **Documentation drift is a bug.** Any change to behavior, public
   API, configuration, or architecture MUST update the matching docs:
   `README.md` + `README_ZH.md`, `CLAUDE.md` Project Context, inline
   docstrings, `docs/ARCHITECTURE.md` + ZH, and `docs/AGNO_MIGRATION_TRACKER.md`
   if it touches the migration ledger.

6. **No mocked DB in integration tests.** We learned this the hard way:
   tests passing against mocks while production migrations broke. Hit a
   real (sqlite or postgres) DB.

## Project layout

See `CLAUDE.md` for the full working-directories tree. Quick orientation:

```
apps/
  backend/   FastAPI + Agno Agent + AgentOS + APScheduler (Python 3.11)
  frontend/  Next.js 14 App Router + Tailwind + Recharts (SSE single transport)
docs/
  ARCHITECTURE.md        DDD layers, scheduler topology, three-way state
  AGNO_MIGRATION_TRACKER.md   T1–T10 + Acceptance 1–4 ledger
.github/
  workflows/ci.yml       backend pytest, frontend lint, ReliabilityEval
.omc/                    spec / plan / autopilot artifacts (planning only)
```

## Dev environment

### Required
- Python 3.11
- Node.js 20+
- Docker + Docker Compose (for the Postgres + pgvector + AgentOS path)
- `uv` (`pipx install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Recommended
- DeepSeek API key (chat) for `LLM_API_KEY`
- A Gate.io **testnet** account (mainnet trading defaults are off — see
  `GATE_USE_TESTNET=true` in `.env.example`)

### First boot
```bash
git clone https://github.com/<your-fork>/llmtrading.git
cd llmtrading
cp .env.example .env                # fill in LLM_API_KEY at minimum
docker compose up -d                # postgres + db-init + backend + frontend
docker compose logs backend --tail 100
open http://localhost:3000/dashboard
```

## Tests

| What | Where | Command |
|---|---|---|
| Backend unit + integration | `apps/backend/tests/` | `cd apps/backend && uv run pytest -m "not manual_qa"` |
| Backend evals (Reliability + Accuracy) | `tests/eval/` | `uv run pytest -m eval` |
| Backend manual_qa (live LLM) | various | `uv run pytest -m manual_qa` (requires `LLM_API_KEY`) |
| Frontend lint | `apps/frontend/` | `npm run lint` |
| Frontend unit (vitest) | `apps/frontend/components/__tests__/` | `npm run test` |
| Frontend E2E (Playwright) | `apps/frontend/tests/e2e/` | `npm run test:e2e` |
| Acceptance 3 — 11 strategies | `tests/agents/test_strategies_acceptance3.py` | included in default lane |
| Spec acceptance 4 (legacy imports) | repo-wide | `rg "from langgraph\|from langchain\|import litellm\|import mcp2py" apps/backend/src/` should be 0 |

The default backend lane runs in <30s. The full suite + frontend lint
should take under a minute on a modern laptop.

## Commit & PR style

We use Conventional Commits with a project scope:

```
feat(backend):  new feature in backend
fix(frontend):  bug fix in frontend
docs:           documentation only
test(backend):  test-only changes
chore(infra):   tooling / CI / build
refactor:       no behavior change
```

- First line ≤ 70 chars
- Body explains **why**, not what (the diff shows what)
- AI-assisted commits should include a `Co-Authored-By:` footer

Branching:
- Feature branches off `main`
- Rebase before opening the PR (no merge commits)
- Squash on merge by default (small fixes); keep history for big features

## PR checklist

Before requesting review, confirm:

- [ ] `uv run pytest -m "not manual_qa"` from `apps/backend/` is green
- [ ] `npm run lint` from `apps/frontend/` is clean
- [ ] If you touched anything user-visible, you walked G1–G6 from
      `CLAUDE.md` against your local stack and have a screenshot or
      curl output to show
- [ ] If you added a public API, schema, or env var, you updated
      `.env.example` (root + `apps/backend/`), the relevant README,
      and `CLAUDE.md` Project Context
- [ ] No new dependency outside the existing license whitelist
      (MIT / Apache-2.0 / BSD / ISC / MPL-2.0). If unsure, list it in
      the PR.
- [ ] No secrets in tracked files (run `git diff --cached | rg "sk-[A-Za-z0-9]{20,}"` to be sure)

## Reporting bugs / requesting features

Please use the issue templates under `.github/ISSUE_TEMPLATE/`. For
security issues, follow `SECURITY.md` instead — do **not** open a
public issue.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
By participating you agree to abide by it.
