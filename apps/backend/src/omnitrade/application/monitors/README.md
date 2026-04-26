# Application monitors — P1 waiver

The Phase-5 monitors are the single place where the **domain → infrastructure
→ application** dependency direction legitimately bends: they own a
periodic tick and therefore must hold references to both a
`PositionRepository` (infra) and the `apply_three_way_state` domain
service. Consensus plan §5 P1 explicitly waives the otherwise-strict
layering rule for this directory only.

Rules the monitors still honour:

1. **Domain stays pure.** Files under `src/omnitrade/domain/` must not
   import from infra/app/agents. Grep gate:
   `rg -n 'from omnitrade\.(infrastructure|application|agents|api)' apps/backend/src/omnitrade/domain/ | wc -l` → `0`.
2. **Three-way state atomicity.** Every close path (trailing_stop,
   stop_loss, partial_profit, position_manager, trade-execution tool)
   routes state mutations through `PositionRepository.apply_three_way_state`.
   Grep gate:
   `rg -n apply_three_way_state apps/backend/src/omnitrade/application/` → ≥ 3 usages.
3. **5 monitors, not folded.** `partial_profit_monitor.py` stays a
   separate file; it is NOT merged into `trailing_stop_monitor.py`.
   Grep gate:
   `grep -l 'partial_profit\|cumulative_close_pct' apps/backend/src/omnitrade/application/monitors/trailing_stop_monitor.py` → empty.
4. **Clock injection.** Every monitor takes a `ClockProtocol` so tests are
   deterministic under `freezegun` or hand-rolled stub clocks.
5. **LLM-framework scope.** Monitors must not import Agno or any other
   LLM framework; only `agents/trading_agent.py` may. This keeps the
   orchestrator free of framework bleed.

Each monitor exposes two public surfaces:

- `interval_seconds: float` — cadence the scheduler should drive it at.
- `async def tick() -> None` — idempotent single-step entry point.

The scheduler never introspects monitor internals; it only calls
`tick()`. The monitor owns its own logging via `with_context(logger)`
(bare-logger gate).
