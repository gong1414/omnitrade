<!--
Thanks for the PR! Read CONTRIBUTING.md before requesting review — the
hard rules there have all earned themselves through real incidents.
-->

## Summary

<!-- 1-3 bullets. Why this change exists, not what the diff shows. -->

-

## Changes

<!-- File-level overview if it helps the reviewer. Not required for
     small PRs. -->

## Related

<!-- Issue / spec / autopilot artefact this PR fulfils. -->

- Closes #
- Spec / plan: `.omc/specs/...` or `.omc/plans/...`

## Test plan

- [ ] `cd apps/backend && uv run pytest -m "not manual_qa"` — green
- [ ] `cd apps/backend && uv run ruff check .` — clean
- [ ] `cd apps/frontend && npm run lint` — clean
- [ ] `cd apps/frontend && npm run test` — green (if frontend touched)
- [ ] Frozen-fixture replay clean (if agent behaviour changed,
      re-record and call out the diff below)

## User-visible acceptance gates

If this changes anything the operator can see, walk the gates from
`CLAUDE.md` against your local stack and tick what applies. Attach
screenshots / `curl` output for G2/G3.

- [ ] G1 — `curl -X POST http://localhost:8000/api/v1/cycle/trigger`
      returns `{"status":"ok"}` in ≤ 60 s
- [ ] G2 — every field in `GET /api/v1/decisions?limit=1` is sane
      (`positions_count`, `market_context`, `gates_passed`,
      `invalidation_condition`, `plan`, `structured_confidence`,
      `output_language`, `iteration`)
- [ ] G3 — dashboard renders the latest decision in the structured
      5-panel layout, switches language with `OUTPUT_LANGUAGE`
- [ ] G4 — scheduler runs ≥ 3 cycles back-to-back without exceptions
- [ ] G5 — no fault phrases in the AI's reasoning text
- [ ] G6 — AI's `positions_count` matches `GET /api/v1/positions`

## Documentation drift

- [ ] `README.md` + `README_ZH.md` updated where applicable
- [ ] `CLAUDE.md` Project Context updated for behaviour / API changes
- [ ] `docs/ARCHITECTURE.md` + `_ZH` updated for layer / topology
      changes
- [ ] `docs/AGNO_MIGRATION_TRACKER.md` updated if this touches the
      migration ledger
- [ ] Inline docstrings cover the new public surface
- [ ] `.env.example` (root + `apps/backend/`) updated for any new env
      var

## Risk

<!-- Anything reviewers should pay extra attention to: state-machine
     changes, three-way state writes, exchange interactions, secret
     handling, anything user-funds-adjacent. -->

## Rollback plan

<!-- How to undo this if it misbehaves in production. Feature flag,
     env knob, or "revert the commit" all valid answers. -->
