# omnitrade · backend

<p>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-CA2136?style=flat">
  <img src="https://img.shields.io/badge/Tests-642_green-2BB673?style=flat">
</p>

Python 3.11 backend for the [OmniTrade](../../README.md) LLM-driven crypto-futures arena. DDD layered, `uv`-managed, FastAPI surface, APScheduler 5-loop engine.

## Layout

| Path | Role |
|---|---|
| `src/omnitrade/domain/` | Pure entities, value objects, protocols, classifier |
| `src/omnitrade/application/` | Services, 5 monitors, multi-agent orchestrator |
| `src/omnitrade/infrastructure/` | Exchange (ccxt), LLM (LiteLLM), persistence, WebSocket |
| `src/omnitrade/agents/` | LangGraph think-node + prompts (the only module that imports `langgraph`) |
| `src/omnitrade/api/` | FastAPI routers + middleware + DI container |
| `src/omnitrade/observability/` | Structlog, correlation-id middleware, trace context |

## Dev loop

```bash
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn omnitrade.api.app:create_app --factory --reload --port 8000
```

## Tests

```bash
uv run pytest                                                                  # full suite
uv run pytest -m "not manual_qa"                                               # CI-safe subset
uv run pytest tests/agents/test_structured_output_contract.py                 # structured-output contract gate
uv run pytest tests/agents/test_tool_aware_gate.py                            # tool-aware regression gate
uv run pytest tests/infrastructure/persistence/test_alembic_0002.py           # schema-rename round-trip
```

## Migrations

```bash
uv run alembic upgrade head             # apply all
uv run alembic downgrade -1             # revert one
uv run alembic history                  # list revisions
```

Revisions:
- `0001` initial schema — 8 tables
- `0002` rename position columns (`peak_pnl_percent` → `trailing_peak_pnl_pct`, `partial_close_percentage` → `cumulative_close_pct`) via `batch_alter_table`

## See also

- [../../README.md](../../README.md) — top-level overview
- [../../docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — DDD layers + 5-loop diagram + three-way state
- [../../docs/STRATEGIES.md](../../docs/STRATEGIES.md) — 11 strategy parameter tables
