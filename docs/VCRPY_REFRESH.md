<p align="right">
  <b>English</b> | <a href="./VCRPY_REFRESH_ZH.md">简体中文</a>
</p>

# OmniTrade — VCR Cassette Refresh Runbook

> When the LLM provider changes its API shape, the recorded VCR cassettes no longer match live responses and the behavioural-equivalence characterization gate starts returning false negatives. This document describes when and how to re-record cassettes without leaking secrets.
>
> This gate is **characterization**, not byte-exact parity; see `.omc/plans/phase-8-oracle-spike-report.md`.

---

## 1. When to refresh

Refresh cassettes **only** when one of these is true:

1. **LLM provider changed response schema** — e.g., DeepSeek adds a new `reasoning` field, OpenAI-compatible providers tweak `choices[].message.content` shape, or the tool-call envelope migrates from `function_call` to `tool_calls`.
2. **Model upgrade** — bumping `LLM_MODEL_NAME` (e.g., `deepseek-v3.2-exp → deepseek-v4`) where the new model produces semantically different outputs that still must pass parity.
3. **Provider swap** — switching from DeepSeek to OpenRouter / native OpenAI / Claude; cassettes encode provider-specific headers that vcrpy uses for matching.
4. **New frozen fixture added** — if you introduce a 23rd snapshot to `tests/fixtures/frozen/`, you must record the corresponding cassette before the characterization gate will pass.

**Do NOT refresh** for:

- Flaky individual test (investigate the test first)
- Characterization score just under 0.95 (investigate the decision diff first)
- Network hiccups (re-run — cassettes are meant to eliminate this)

If the characterization score regresses but you cannot identify an LLM API change, open an issue labelled `characterization-regression` and **do not** refresh. Silent refreshes mask real behavioural drift.

---

## 2. Prerequisites

- A **live API key** with sufficient quota for 22 replays (budget ~20 k tokens per fixture ≈ 450 k tokens total).
- Frozen fixtures under `tests/fixtures/frozen/market_snapshots/` and `tests/fixtures/frozen/baseline_decisions/` **unchanged** (they are the ground truth; only cassettes refresh).
- Clean Git working tree so the cassette diff is reviewable.
- `uv` on PATH and `apps/backend/.venv/` synced (`cd apps/backend && uv sync --all-extras`).
- `VCR_RECORD_MODE=once` — record missing interactions, never overwrite existing ones. Use `all` only when you truly want to replace everything.

Set the key in a local file that is **not committed**:

```bash
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL_NAME="deepseek/deepseek-v3.2-exp"
```

---

## 3. Procedure

### 3.1 Back up existing cassettes

```bash
cd apps/backend/tests/behavioral_equivalence
cp -R cassettes cassettes.bak-$(date +%Y%m%d)
ls cassettes.bak-*/ | wc -l        # sanity — same count as cassettes/
cd ../../../..
```

### 3.2 Delete the cassette(s) you want to refresh

For a single fixture:

```bash
rm apps/backend/tests/behavioral_equivalence/cassettes/case_13_autopilot_close_full.yaml
```

For a full refresh (rare):

```bash
rm apps/backend/tests/behavioral_equivalence/cassettes/snapshot_*.yaml
```

Do **not** delete `_smoke_roundtrip.yaml` unless the smoke test itself is failing.

### 3.3 Re-record against live API

With `VCR_RECORD_MODE=once`, the characterization test will re-record any deleted cassettes and reuse any existing ones:

```bash
cd apps/backend
VCR_RECORD_MODE=once uv run pytest tests/behavioral_equivalence/test_decision_characterization.py -q
```

Expected: the deleted cassettes are re-created; all other cassettes replay from disk. No live call is made for cassettes that already exist.

### 3.4 Inspect the diff

```bash
git diff -- apps/backend/tests/behavioral_equivalence/cassettes/
```

Acceptable diffs (semantic changes):

- New fields in response body (e.g., `usage.reasoning_tokens`)
- Reordered keys in JSON (YAML canonicalises, but model may reorder)
- Updated model version string
- New `tool_calls` envelope if the provider added one

Reject the diff and investigate if you see:

- Completely different decision text (`buy` → `sell` etc.) — implies real behavioural drift
- Empty / truncated response body — implies rate-limit or partial failure during recording
- Unexpected header changes the test asserts on

### 3.5 Verify characterization gate

```bash
cd ../..
uv --project apps/backend run python scripts/run_characterization.py \
  --fixtures tests/fixtures/frozen/ \
  --cassettes apps/backend/tests/behavioral_equivalence/cassettes/ \
  --threshold 0.95 \
  --report apps/backend/tests/behavioral_equivalence/reports/refresh-check.json
```

If the characterization pass-rate ≥ 0.95, proceed. Otherwise, **do not** commit the refresh — roll back (`rm -rf apps/backend/tests/behavioral_equivalence/cassettes && mv cassettes.bak-* cassettes`) and open a regression issue.

### 3.6 Commit

```bash
git add apps/backend/tests/behavioral_equivalence/cassettes/
git commit -m "chore(characterization): refresh cassettes for <provider/model reason>"
```

Keep the commit atomic — cassette refreshes should not be mixed with source changes.

### 3.7 Remove the backup once the refresh is verified

```bash
rm -rf apps/backend/tests/behavioral_equivalence/cassettes.bak-*
```

---

## 4. Safety: never commit secrets

`conftest.py` configures vcrpy with a set of filters that strip sensitive headers before the cassette is persisted. Before committing any refresh, double-check:

```bash
rg -i 'authorization|api[-_]?key|bearer|sk-[A-Za-z0-9]+' \
   apps/backend/tests/behavioral_equivalence/cassettes/
# expected: empty
```

If any match comes back, **stop**. Do not `git commit`. Update `conftest.py`'s `filter_headers` list to include the leaked header name, delete the compromised cassettes, and re-run §3.

Minimum filter set that must remain in `conftest.py`:

```python
my_vcr = vcr.VCR(
    filter_headers=[
        "authorization",
        "x-api-key",
        "openai-api-key",
        "cookie",
        "set-cookie",
    ],
    filter_query_parameters=["api_key", "token"],
    filter_post_data_parameters=["api_key"],
)
```

Also verify no raw bearer tokens appear inline in YAML:

```bash
rg -n 'Bearer sk-' apps/backend/tests/behavioral_equivalence/cassettes/
# expected: empty
```

---

## 5. Advanced: per-interaction refresh

If only one specific interaction inside a cassette changed (e.g., one of three LLM calls in `case_14_autopilot_close_partial.yaml`), you can edit the YAML by hand — cassettes are plain text. Always verify with `yamllint` and replay before committing:

```bash
yamllint apps/backend/tests/behavioral_equivalence/cassettes/snapshot_14_*.yaml
uv --project apps/backend run pytest tests/behavioral_equivalence/test_cassette_roundtrip.py -k snapshot_14 -q
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `CannotOverwriteExistingCassetteException` | Re-record attempted with `record_mode=once` while cassette still exists | Delete the cassette (§3.2) first, then re-run |
| `<fixture>.yaml: empty` after record | Network blocked on recording machine | Retry with longer timeout; ensure outbound HTTPS open |
| Characterization pass-rate drops from 1.00 → 0.93 after refresh | Model update changed decision text | Either accept (update upstream baseline) or rollback |
| Secret leak in cassette | Missing filter in `conftest.py` | Add to `filter_headers`; delete + re-record |
| Cassette refresh fails on CI | CI has no live API key — by design | Refreshes are **local-only**; commit pre-recorded cassettes |

---

## Oracle Feasibility Spike Addendum (2026-04-18)

**Verdict:** byte-exact v2 baseline not feasible — gate is **characterization**, not parity.
**Evidence:** see `.omc/plans/phase-8-oracle-spike-report.md`.

The 22 `tests/fixtures/frozen/baseline_decisions/decision_NN_*.json` files are hand-curated contracts (human prose `notes`, manual arithmetic, explicit `EDGE CASE` markers, no provenance fields, no raw LLM bytes). ~59% of baselines (13/22 monitor-initiated closes — `trailing_stop` / `stop_loss` / `partial_profit`) correspond to cycles that never call the LLM by architecture — there is nothing to replay at the LLM layer. `apps/backend/tests/behavioral_equivalence/_cassette_synth.py` explicitly synthesises cassettes deterministically from the baseline JSONs ("pure — no network"). The 22/22 gate therefore locks regression against the frozen hand-curated contract. This runbook's core VCR workflow remains valid for refreshing cassettes when the Python-side LLM provider contract shifts.
