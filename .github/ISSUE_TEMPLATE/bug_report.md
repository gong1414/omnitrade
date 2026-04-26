---
name: Bug report
about: Something is broken or behaving unexpectedly
title: "[bug] "
labels: bug
assignees: ""
---

## Summary

<!-- One sentence: what's broken? -->

## Reproduction

Minimal steps for someone else to hit the same issue:

1.
2.
3.

If it's reproducible only against a specific strategy, list it
(e.g. `arena-tribunal`, `arena-raider-squad`, …).

## Expected vs actual

- **Expected**:
- **Actual**:

## Environment

- OmniTrade commit / tag:
- OS + arch (e.g. macOS 14 / arm64, Linux x86_64):
- Python: `python --version`
- Node: `node --version`
- Docker: `docker --version`
- Postgres image (`docker compose ps postgres`): `pgvector/pgvector:pg16` (default) or other
- LLM provider + model (`AGNO_LLM_MODEL`):
- Embedder provider (`EMBEDDER_PROVIDER`): `fastembed` (default) or `openai`
- Exchange (`EXCHANGE`) + testnet flag (`GATE_USE_TESTNET` / `OKX_USE_TESTNET`):
- Scheduler driver (`AGNO_SCHEDULER_DRIVES_CYCLE`):

## Logs / decision JSON

```
<!-- Paste relevant output. The most useful artefacts:
     - `docker compose logs backend --tail 200`
     - `curl -s http://localhost:8000/api/v1/decisions?limit=1 | jq`
     - browser console errors (for dashboard bugs)
     Strip API keys before pasting!
-->
```

## What you've already tried

<!-- Helps avoid the obvious dead ends. -->

## Severity

- [ ] Blocking — system unusable
- [ ] High — feature broken, no workaround
- [ ] Medium — feature broken, workaround exists
- [ ] Low — cosmetic / minor
