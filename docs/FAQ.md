# FAQ — common questions and recurring errors

If you hit something that's not in here, please [open an issue][issues]
— we'll add it.

[issues]: https://github.com/gong1414/omnitrade/issues

## Setup

### Q: I only have an OpenAI / OpenRouter key, can I use that instead of DeepSeek?

Yes. OmniTrade is built on Agno's `DeepSeek` model class but the underlying
HTTP layer is OpenAI-compatible. Set:

```env
LLM_API_KEY=sk-...                     # your OpenAI / OpenRouter key
LLM_BASE_URL=https://api.openai.com/v1 # or OpenRouter / aggregator base
AGNO_LLM_MODEL=gpt-5.4                 # or whatever model the provider serves
```

For embeddings, also flip:

```env
EMBEDDER_PROVIDER=openai
EMBEDDER_API_KEY=sk-...                # same key usually works
EMBEDDER_BASE_URL=https://api.openai.com/v1
```

### Q: First boot hangs at "Downloading BAAI/bge-small-en-v1.5"

The embedder model downloads from `huggingface.co` on first run. If you're
on a Chinese network, the default TLS handshake times out. We already
route through `https://hf-mirror.com` via the `HF_ENDPOINT` env in
`docker-compose.yml`, so this should "just work" — but if it still hangs:

```bash
docker compose logs backend --tail 50
# look for HFError / SSL / connection timeout
```

If you see SSL errors, your network is also blocking `hf-mirror.com`.
Workaround: download `BAAI/bge-small-en-v1.5` manually to
`./hf_cache/huggingface/hub/` (the volume mount), then restart.

### Q: How do I run without Docker?

See README.md → Path B (local Python 3.11 + Node 20). You'll need
`uv`, a running Postgres + pgvector instance somewhere, and to set
`DATABASE_URL` in `.env` accordingly.

## Runtime

### Q: `curl /api/v1/cycle/trigger` returns 504 / takes >60 s

Likely causes, in order:

1. **The reasoner model is slow.** `deepseek-reasoner` on the tribunal
   strategy routinely takes 100–200 s. Bump
   `cycle_trigger_timeout_seconds` (default 60) to 180+, or switch
   `AGNO_LLM_MODEL` to `deepseek-v4-flash` for faster cycles.
2. **Rate limiting.** Check the backend logs for HTTP 429 on the LLM
   provider. DeepSeek's free tier is generous but not infinite.
3. **MCP server hung.** One of the 15 MCP tool servers (9 trading + 6
   crypto data) might be timing out. The 10s monitor cycle should keep
   running even if the main think function is stuck — check
   `docker compose logs backend | grep -i mcp`.

### Q: The AI's `market_context` says "数据同步故障 / data sync issue"

This is the **G5 fault-phrase guardrail** firing. Treat it as a bug
ticket: the AI is reporting that something it observed doesn't match
reality. Most often it means the position-sync worker hasn't caught up
yet, or the exchange is returning malformed data. Check:

```bash
curl -s http://localhost:8000/api/v1/positions | jq
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq '.positions_count'
# These two MUST agree. If they don't, that's a G6 cross-source bug.
```

### Q: Opens above $10 000 just hang / don't fire

That's the **T9 HITL gate** doing its job. Opens with USD notional
above `HITL_OPEN_SIZE_THRESHOLD_USD` (default 10 000) pause and wait
for operator approval. Look for the approval banner on
`http://localhost:3000/dashboard` and click Approve / Reject. Or via API:

```bash
curl -X POST http://localhost:8000/api/v1/runs/{run_id}/confirm
```

To raise the threshold:

```env
HITL_OPEN_SIZE_THRESHOLD_USD=50000
```

To disable entirely (not recommended on mainnet):

```env
HITL_OPEN_SIZE_THRESHOLD_USD=0
```

(Not 0 — you can't disable; set to a value like `99999999` to
effectively disable.)

### Q: `daily_loss_cap` triggered, all decisions show as `hold`

The **DailyLossLimiter** is rewriting open / close / partial_close to
`hold` because today's realized PnL dropped below
`-DAILY_LOSS_CAP_USDT`. This resets at UTC midnight. To raise the cap:

```env
DAILY_LOSS_CAP_USDT=500.0
```

### Q: How do I switch strategies without restarting?

Right now you have to restart the backend after changing
`TRADING_STRATEGY` — the strategy is loaded once at boot. A hot-swap
endpoint is on the roadmap; if you'd find it useful, +1 the issue or
PR a draft.

## Development

### Q: pytest is failing with `psycopg.OperationalError`

The backend test suite uses SQLite by default (via `aiosqlite`). If
you see psycopg errors, your `DATABASE_URL` is pointing at Postgres
but the Postgres service isn't reachable. Either start Postgres
(`docker compose up postgres`) or override:

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/test.db uv run pytest
```

### Q: My PR's CI fails on `mypy --strict`

OmniTrade pins `mypy --strict` because the agent's tool layer is
type-sensitive (one wrongly-typed kwarg silently breaks tool-calling).
The PR template has the local commands you should run before pushing.

### Q: Can I add a new strategy?

Yes. The minimum viable patch:

1. Add a new member to `domain/enums.py::StrategyName`
2. Drop a new prompt file in `agents/prompts/`
3. Wire the strategy into `agents/trading_agent.py::build_agno_think_fn`'s
   strategy selector
4. Add a row to `tests/agents/test_strategies_acceptance3.py` — every
   strategy must complete a cycle deterministically (no LLM calls)
5. Update `docs/STRATEGIES.md`

The 22 frozen-fixture replay gate must still pass at ≥ 0.95.

## Operations

### Q: How do I monitor cycles in production?

Every cycle emits an OpenTelemetry span tree (T4). The simplest path:

```bash
curl -s http://localhost:8000/traces | jq    # AgentOS trace API
```

Each span shows model calls, tool calls, and durations. For longer-term
storage, point your existing OTel collector at the backend (Agno's
tracing setup respects standard `OTEL_*` env).

### Q: How do I scale this beyond one operator?

The current design assumes a single operator per deployment.
Multi-tenant support (per-user trading accounts, isolated agent state)
is **not** in 1.0. If that's a use case for you, please open an issue
to discuss the shape — it's a substantial design decision.
