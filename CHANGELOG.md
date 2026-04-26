# Changelog

All notable changes to OmniTrade are documented here. The format is
loosely based on [Keep a Changelog][kac]; the project follows
[Semantic Versioning][semver] but is currently pre-1.0 and on a rolling
release cadence — breaking changes are still possible between minor
bumps until 1.0.0.

[kac]: https://keepachangelog.com/en/1.1.0/
[semver]: https://semver.org/spec/v2.0.0.html

## [Unreleased]

Post-v0.1.0 OSS-hardening pass. Future bumps will be cut by
release-please from conventional commits.

### Added
- **OSS quality / safety stack**:
  - CodeQL code scanning (advanced setup, weekly cron + push)
  - Copilot Autofix (built-in, free for public repos)
  - Dependabot vulnerability alerts + security updates
  - Dependabot grouped version-update PRs (majors blocked, minors+patches grouped)
  - Secret scanning + push protection
  - OpenSSF Scorecard workflow + badge (supply-chain score)
  - dependency-review-action (PR-time CVE/license gate, fail on moderate+)
  - Codecov coverage upload + badge
  - markdown-link-check (weekly cron + per-PR)
  - PR auto-labeler with 9 path-based rules
  - Auto-format-on-PR workflow (`ruff format` + `ruff check --fix-only`,
    same-repo PRs only)
  - release-please for changelog + tag automation
- **Open-source release prep**: `CONTRIBUTING.md` (+ ZH), `SECURITY.md`
  (+ ZH), `CODE_OF_CONDUCT.md` (+ ZH), `TRADEMARKS.md` (+ ZH),
  `DEVELOPMENT.md` (+ ZH), `docs/QUICKSTART.md` (+ ZH),
  `docs/FAQ.md` (+ ZH), `docs/adr/` directory with first two
  Architecture Decision Records, GitHub issue forms (YAML) + PR
  template, `[project.urls]` in `apps/backend/pyproject.toml`,
  ⚠️ risk disclaimer in both READMEs.
- **Refreshed `.env.example`** (root + `apps/backend/`) covering all
  knobs introduced by T1–T10: `HF_ENDPOINT`, `EMBEDDER_PROVIDER`,
  `EMBEDDER_API_KEY`, `EMBEDDER_BASE_URL`, `EMBEDDER_MODEL_ID`,
  `HITL_OPEN_SIZE_THRESHOLD_USD`, `HITL_APPROVAL_WAIT_SECONDS`,
  `OTEL_TRACING_ENABLED`, `AGNO_LLM_MODEL`, `AGNO_POSTGRES_URL`,
  `AGNO_SCHEDULER_DRIVES_CYCLE`.
- **Sponsorship surface**: `.github/FUNDING.yml` + USDT-TRC20 address
  with QR in README.
- **Brand assets**: hand-authored `assets/{logo,logo-horizontal,
  favicon,logo-mono,sponsor-usdt-trc20}.svg` and `social-preview.png`.

### Changed
- `docker-compose.prod.yml` header comment no longer mentions SQLite —
  the prod path is Postgres + pgvector, same as dev.
- README slimmed via `<details>` collapsibles (visible length
  ~280 lines vs original ~590) and front-loaded with News / Try in 2
  Min / Use Cases / vs Hand-rolled sections.

### Fixed
- 86 CodeQL code-scanning findings closed (13 real fixes + 59
  documented false-positive dismissals + 14 auto-resolved by code
  edits).
- `Money.__add__/__sub__` now raise `ArithmeticError` instead of
  `ValueError` (matches the special-method contract).
- `leverage_bands.get_leverage_band` refactored from `match-case` to
  dict lookup so static-analysis sees a single return profile.

## [Agno cutover + T1–T10 hardening] — 2026-04-26

The 4-acceptance Agno migration spec is fully green and the T1–T10
hardening passes shipped on top of it. See
[`docs/AGNO_MIGRATION_TRACKER.md`](docs/AGNO_MIGRATION_TRACKER.md) for
the full per-task ledger.

### Added
- **T1 — Native Agno retries** via `Agent(retries=...)` instead of
  the previous custom backoff layer.
- **T2 — Cross-cycle session summaries**: `enable_session_summaries=True`
  + `add_history_to_context=True` + `num_history_runs=5`, persisted to
  `ai.agno_sessions.summary` per `_TRADING_SESSION_ID`.
- **T3 — G5 fault-phrase post-hook** in
  `agents/guardrails/qa_phrase.py` — scans `RunOutput.content` for the
  11 known failure phrases (`异常`, `数据同步故障`,
  `所有 X 都是 0`, `inconsistent`, `system issue`, …) and publishes
  `EVENT_ORCHESTRATOR_ERROR` on hit so the dashboard banner lights up
  automatically.
- **T4 — OpenTelemetry tracing overlay**: `agno.tracing.setup_tracing`
  + OpenInference `AgnoInstrumentor` writes spans to `ai.agno_spans`,
  exposed via AgentOS `GET /traces`. Idempotent;
  `OTEL_TRACING_ENABLED=false` disables.
- **T7 — `Agent ReliabilityEval`** under
  `tests/eval/test_reliability_cycle.py`, runs in its own CI step
  under `pytest -m eval`.
- **T8 — `AccuracyEval`** under `tests/eval/test_accuracy_g2.py` —
  cassette-gated, exercises a real LLM judge.
- **T9 — Human-in-the-loop large-open gate**: opens with USD notional
  above `HITL_OPEN_SIZE_THRESHOLD_USD` (default 10 000) pause via
  `EVENT_RUN_PAUSED` SSE + `POST /api/v1/runs/{id}/{confirm,reject}`
  endpoints + dashboard `ApprovalBanner.tsx`. Wrapper sits on the
  `record_open_decision` tool itself, so any new open path inherits
  the gate.
- **T10 — Trade-journal RAG**: every cycle's `StructuredReason` is
  serialised and ingested into `ai.trade_journal` (PgVector hybrid
  search). Subsequent cycles auto-inject the most semantically
  relevant prior decisions into the system prompt
  (`search_knowledge=True`).
- **`pgvector/pgvector:pg16` Postgres image** (drop-in for
  `postgres:16-alpine`, same PG major).
- **Local fastembed embedder** (`BAAI/bge-small-en-v1.5`, 384-dim, no
  API key) as the default — DeepSeek's API doesn't expose
  `/v1/embeddings`. The OpenAI-protocol embedder path is still
  available via `EMBEDDER_PROVIDER=openai`.
- **`HF_ENDPOINT=https://hf-mirror.com`** + persistent `hf_cache`
  Docker volume — huggingface.co's TLS handshake is unreliable on cn
  networks.
- **Acceptance 3 deterministic gate** —
  `tests/agents/test_strategies_acceptance3.py`: 12 tests (1 sanity +
  11 parametrised over `StrategyName`) verify every strategy's
  `build_agno_think_fn` produces a valid `Decision` without hitting an
  LLM.
- **AgentOS native scheduler** drives the trading-cycle Workflow (15s
  poll) when `AGNO_SCHEDULER_DRIVES_CYCLE=true`. APScheduler keeps the
  6 fast position-protection monitors (`account_recorder`,
  `trailing_stop`, `stop_loss`, `partial_profit`, 10 s cadence).

### Changed
- **Single LLM/Agent/MCP framework**: Agno 2.x is now the only path.
  `rg "from langgraph|from langchain|import litellm|import mcp2py"
  apps/backend/src/` returns 0.
- **DeepSeek via Agno's native model class** —
  `Agent(model=DeepSeek(id=...))` reads `LLM_API_KEY` +
  `LLM_BASE_URL=https://api.deepseek.com/v1`. LiteLLM has been
  removed end-to-end.
- **9 trading + 6 crypto-data MCP tools** loaded via Agno's
  `MultiMCPTools` (formerly mcp2py — fully removed).
- **Single Agno Agent** for 9 strategies, optional Agno Team
  (coordinate mode) for `arena-tribunal` + `arena-raider-squad` only.
- **Schema rename**: `agent_decisions.correlation_id → run_id` (T5+T6).
  Migration `0006_rename_correlation_id_to_run_id` uses
  `op.batch_alter_table` for SQLite compatibility. The remaining
  `correlation_id` references are the orthogonal HTTP-request-trace
  ContextVar layer in `observability/trace_context.py`.
- **Default OpenAI embedder → fastembed** (see Added).

### Removed
- LangGraph, LangChain, LiteLLM, mcp2py, the WebSocket transport, the
  custom retry loop, and the SQLite-vec embedding sink. All of them
  are now load-bearing zero — `rg` confirms.

### Fixed
- **Phantom positions** — `fetch_positions` reads `contracts` only,
  never `contractSize`. Cross-source consistency check (G6) wired into
  the cycle so any disagreement between the AI's
  `positions_count` and `/api/v1/positions` is a build break.
- **Stale `llmtrading-db-init` image** — added `db-init` profile +
  `condition: service_completed_successfully` so `docker compose up`
  re-runs migrations on every boot rather than reusing a cached image.

## Earlier history

For pre-cutover history (the TS → Python DDD rewrite, the original
LiteLLM stack, the 22-fixture characterization gate that pinned
behaviour through the migration), see `git log` and the per-PR
post-mortems linked from
[`docs/AGNO_MIGRATION_TRACKER.md`](docs/AGNO_MIGRATION_TRACKER.md).
