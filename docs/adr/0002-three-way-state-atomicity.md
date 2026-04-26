# ADR 0002 — Three-way state atomicity for position lifecycle

- **Status**: Accepted (2026-04-26)
- **Deciders**: maintainers
- **Related**: `apps/backend/src/omnitrade/infrastructure/persistence/repositories/position_repository.py::apply_three_way_state`

## Context

A position's lifecycle is governed by three numerical fields that
together encode "how much of this position has already been closed,
where the stop-loss currently sits, and how high the trailing peak has
ridden":

| Field | Semantics |
|---|---|
| `cumulative_close_pct` | Percent of original size already closed (0–100) |
| `stop_loss` | The current stop-loss price (mutates as trailing tightens) |
| `trailing_peak_pnl_pct` | Highest unrealised PnL %, the trailing-stop ladder hangs off this |

These fields are read together by the **3 fast monitors** running every
10 seconds (`stop_loss_monitor`, `trailing_stop_monitor`,
`partial_profit_monitor`) and every cycle's AI agent. Any of those
readers seeing a torn write — for example, `cumulative_close_pct=50` but
`stop_loss` still pointing at the pre-close level — produces
catastrophically wrong decisions: double-closes, missed stops, or
drawdowns that didn't actually trigger trailing.

We learnt this the painful way during early Phase-9 work, when a
`partial_profit_monitor` cycle landed `cumulative_close_pct=25`
through one repository call and `trailing_peak_pnl_pct` through a
second. Between the two writes, the `stop_loss_monitor` fired, saw 25%
already closed but the original stop, and skipped a stop that should
have triggered.

## Decision

**Every write that touches `cumulative_close_pct`, `stop_loss`, or
`trailing_peak_pnl_pct` must go through `PositionRepository.apply_three_way_state`,
which lands all three columns in a single SQL `UPDATE`.**

```python
async def apply_three_way_state(
    position_id: int,
    *,
    cumulative_close_pct: Decimal,
    stop_loss: Decimal,
    trailing_peak_pnl_pct: Decimal,
) -> None:
    """All three columns land together. No exceptions, no partial writes."""
```

Direct ORM updates that touch any of these three columns outside this
method are forbidden. CI's brand-scrub-style guard greps for
`stop_loss=` / `cumulative_close_pct=` / `trailing_peak_pnl_pct=` in
`infrastructure/persistence/` and rejects any reference outside the
single repository method.

## Consequences

### Positive

- Readers can never observe a torn three-way state. The atomicity
  contract is upheld by Postgres's row-level write isolation.
- The repository method becomes the single audit point — one place to
  read to understand the full state-machine of a position.
- Easier to add new readers: any new monitor / agent path automatically
  inherits the contract.

### Negative

- Slightly more verbose at call sites (callers must pass all three
  columns, even if updating just one) — mitigated by helper functions
  in `application/services/` that compute the unchanged columns.
- Concurrent writes to the same position serialise on row lock —
  acceptable since position writes are bounded per cycle.

### Neutral

- Schema migration cost: the rename (`peak_pnl_percent →
  trailing_peak_pnl_pct`, `partial_close_percentage →
  cumulative_close_pct`) was painful but already paid for in
  Alembic 0002.

## Compliance

- `CLAUDE.md` lists three-way state atomicity as a hard rule
- `CONTRIBUTING.md` PR checklist includes "any code path touching these
  three columns goes through `apply_three_way_state`"
- The repository method has a module-level docstring linking back to
  this ADR
