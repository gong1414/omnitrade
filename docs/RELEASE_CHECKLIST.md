<p align="right">
  <b>English</b> | <a href="./RELEASE_CHECKLIST_ZH.md">简体中文</a>
</p>

# OmniTrade — Release Checklist (dry-runnable)

> A linear checklist for cutting a production release. Every box has a shell snippet so you can either execute or copy-paste into your runbook.
> **This checklist is advisory** — the maintainer (you) runs the tag and any external publication steps manually. CI only validates; CI never tags or publishes.

Environment assumed: repo root (`/path/to/llmtrading`), `uv` on PATH, `npm` on PATH, Docker daemon running.

---

## 1 · Pre-flight — repo sanity

- [ ] **All previous phase gates green** — inspect each HANDOFF:

  ```bash
  ls HANDOFF-phase-*.md apps/backend/HANDOFF-phase-*.md apps/frontend/HANDOFF-phase-*.md
  ```

  Expected files: phase-0..2 at repo root, phase-3..5 + 4.5 under `apps/backend/`, phase-6 under `apps/frontend/`, phase-7 at repo root.

- [ ] **Clean working tree:**

  ```bash
  git status --short
  # expected: empty
  ```

- [ ] **Verify commit history covers all phases:**

  ```bash
  git log --oneline --grep='phase-' | head -30
  ```

---

## 2 · Backend gates

- [ ] **Ruff lint + format:**

  ```bash
  cd apps/backend
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  ```

- [ ] **mypy strict:**

  ```bash
  uv run mypy --strict src/
  ```

- [ ] **pytest with coverage ≥ 80 %:**

  ```bash
  uv run pytest tests/ -q --cov=src/omnitrade --cov-fail-under=80
  ```

- [ ] **Structured output contract gate:**

  ```bash
  uv run pytest tests/agents/test_structured_output_contract.py tests/agents/test_tool_aware_gate.py -q
  ```

---

## 3 · Frontend gates

- [ ] **Type-check:**

  ```bash
  npm run type-check --workspace apps/frontend
  ```

- [ ] **Lint:**

  ```bash
  npm run lint --workspace apps/frontend
  ```

- [ ] **Production build:**

  ```bash
  npm run build --workspace apps/frontend
  ```

- [ ] **Playwright e2e (Chromium):**

  ```bash
  cd apps/frontend
  npx playwright install --with-deps chromium
  npx playwright test --project=chromium
  cd ../..
  ```

---

## 4 · Docker validity

- [ ] **Dev compose parses:**

  ```bash
  docker compose config >/dev/null && echo "dev: OK"
  ```

- [ ] **Prod compose parses:**

  ```bash
  docker compose -f docker-compose.prod.yml config >/dev/null && echo "prod: OK"
  ```

- [ ] **Images build:**

  ```bash
  docker compose -f docker-compose.prod.yml build --pull
  ```

---

## 5 · Brand scrub

- [ ] **Zero brand leaks in shipped sources:**

  ```bash
  ! rg -n 'NOFIAIOO|195440|nof1\.ai|voltagent' \
      --glob '!docs/history/**' \
      --glob '!node_modules/**' \
      --glob '!.omc/**' \
      --glob '!.venv/**' \
      apps/ docs/ README*.md \
    && echo "brand scrub: CLEAN"
  ```

  Expected: zero matches.

---

## 6 · Secrets / env

- [ ] **`.env.production` exists on the host, NOT in git:**

  ```bash
  test -f .env.production || echo "MISSING .env.production — copy from .env.production.example"
  git ls-files .env.production
  # expected: empty
  ```

- [ ] **Required secrets populated** (non-empty):

  ```bash
  grep -E '^(LLM_API_KEY|GATE_API_KEY|GATE_API_SECRET)=' .env.production | grep -v '=$'
  ```

- [ ] **Testnet flag matches intent:**

  ```bash
  grep -E '^(GATE_USE_TESTNET|OKX_USE_TESTNET|ENVIRONMENT)=' .env.production
  # set to true / testnet for dry-runs
  ```

---

## 7 · Data safety

- [ ] **Backup current production DB:**

  ```bash
  ts=$(date +%Y%m%dT%H%M%S)
  cp data/omnitrade.db "data/omnitrade-${ts}.db.bak"
  ls -lh data/omnitrade-*.db.bak | tail -3
  ```

- [ ] **Dry-run migrations on a copy:**

  ```bash
  cp "data/omnitrade-${ts}.db.bak" /tmp/omnitrade-dryrun.db
  DATABASE_URL=sqlite:////tmp/omnitrade-dryrun.db \
    uv --project apps/backend run alembic upgrade head
  ```

---

## 8 · Deploy

- [ ] **Stop current stack (if running):**

  ```bash
  docker compose -f docker-compose.prod.yml down
  ```

- [ ] **Apply schema migrations:**

  ```bash
  docker compose -f docker-compose.prod.yml run --rm db-init
  ```

- [ ] **Start stack:**

  ```bash
  docker compose -f docker-compose.prod.yml up -d
  ```

---

## 9 · Post-deploy smoke

- [ ] **Health check polling (5 min, or until healthy):**

  ```bash
  for i in $(seq 1 30); do
    status=$(docker inspect --format '{{.State.Health.Status}}' omnitrade-backend 2>/dev/null)
    echo "tick $i: backend=$status"
    [ "$status" = "healthy" ] && break
    sleep 10
  done
  ```

- [ ] **Curl /health:**

  ```bash
  curl -fsS http://localhost:8000/health
  ```

- [ ] **Dashboard serves index:**

  ```bash
  curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/
  # expected: 200
  ```

- [ ] **Observability smoke — correlation id in logs:**

  ```bash
  req_id=$(uuidgen)
  curl -fsS -H "X-Request-ID: $req_id" http://localhost:8000/api/account >/dev/null
  docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -c "$req_id"
  # expected: ≥ 1
  ```

- [ ] **One trading loop completes:**

  ```bash
  docker compose -f docker-compose.prod.yml logs --since=10m backend | \
    grep -E 'trading_loop.*(started|completed)'
  ```

---

## 10 · Tag release (manual — maintainer only)

> Executor agents MUST NOT run this step. Tag signing is a maintainer action.

- [ ] **Create signed tag:**

  ```bash
  git tag -s v1.0.0 -m "v1.0.0 — OmniTrade Python DDD"
  ```

- [ ] **Push tag:**

  ```bash
  git push origin v1.0.0
  ```

---

## 11 · Rollback plan

If health fails or a smoke test misbehaves, roll back:

- [ ] **Stop new stack + restore DB from backup:**

  ```bash
  docker compose -f docker-compose.prod.yml down
  cp "data/omnitrade-${ts}.db.bak" data/omnitrade.db
  ```

- [ ] **Check out previous tag + redeploy:**

  ```bash
  prev_tag=$(git describe --tags --abbrev=0 HEAD^)
  git checkout "$prev_tag"
  docker compose -f docker-compose.prod.yml up -d
  ```

- [ ] **Verify previous version healthy:**

  ```bash
  curl -fsS http://localhost:8000/health
  ```

---

## 12 · Known follow-ups (from consensus plan §4)

These are acknowledged deferrals — none blocks the v1.0.0 release:

- **F-UP 1:** ~~VCR cassette refresh runbook~~ — retired in PR-B2 Phase D; see [VCRPY_REFRESH.md](./VCRPY_REFRESH.md) for historical context.
- **F-UP 2:** Postgres-compatible repository (SQLite is the ship-blocker default).
- **F-UP 3:** Mainnet audit + red-team run — required before flipping `*_USE_TESTNET=false`.
- **F-UP 4:** Add Redis to the default compose (currently gated behind `--profile cache`).
