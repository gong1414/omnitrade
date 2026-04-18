# OmniTrade — Phase-5 Performance Baseline

Captured on 2026-04-18 during Phase-5 close-out. Numbers are **not** a
SLO; they are a reference so Phase-6 refactors can spot regressions.

## Hardware + process

- Host: Apple Silicon laptop (Darwin 25.4.0)
- Python 3.11, uv-managed venv
- In-memory SQLite (`sqlite+aiosqlite:///:memory:`) for all tests
- Cassette LLM + `FakeExchange` — no network I/O

## EventBus publish -> deliver (in-process)

Single publisher, single queue subscriber, 1 000 iterations:

| metric | value |
| ------ | ----- |
| p50 | 13.75 us |
| p95 | 14.75 us |
| p99 | 19.29 us |

Methodology: `tests/perf/bench_event_bus.py` publishes
`EVENT_POSITION_UPDATE`, immediately drains the subscriber queue, and
records `time.perf_counter_ns()` around the round-trip.

## Trading loop one-shot (`run_cycle` + record)

Covered by `tests/integration/test_full_loop.py` — a single pass through
`observe -> think -> risk_check -> execute -> reflect` plus
`DecisionService.record` and `AccountService.record_snapshot` completes
well under the pytest 60 s timeout; no individual test in the 430-test
suite was observed to exceed ~2 s locally.

## REST endpoints

Smoke-tested via `httpx.AsyncClient(ASGITransport)` in
`tests/api/**`. The full API suite (17 tests spanning
account/positions/decisions/config/actions/rebate + IP-blacklist)
completes in under 2 seconds wall-clock on the reference host.

## Notes for Phase-6

- The `SQLAlchemy` SQLite round-trip occasionally returns `0.0` for
  `Decimal("0")` columns (REAL affinity). Phase-6 should move to
  NUMERIC columns on Postgres and assert strict Decimal equality.
- Event bus is single-process; a Phase-6 multi-worker deployment will
  need Redis/NATS pub/sub to fan out across workers.
- The `FastAPIDeprecationWarning: ORJSONResponse` is cosmetic; FastAPI
  now serialises via Pydantic directly. Remove `default_response_class`
  after upgrading the frontend's JSON-parser compatibility matrix.
