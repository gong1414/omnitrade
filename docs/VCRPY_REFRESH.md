<p align="right">
  <b>English</b> | <a href="./VCRPY_REFRESH_ZH.md">简体中文</a>
</p>

# OmniTrade — VCR Cassette Refresh Runbook

> **DEPRECATED — superseded by Phase 9 PR-B2 structured output contract tests.**
>
> The 22-cassette characterization gate and its associated VCR replay infrastructure were retired in PR-B2 Phase D. The cassette directory (`apps/backend/tests/behavioral_equivalence/`) and the driver script (`scripts/run_characterization.py`) have been removed from the repository.

## New regression approach

Regression is now enforced by the structured output contract test suite in `apps/backend/tests/agents/`:

- `tests/agents/test_structured_output_contract.py` — 28 structured-output contract assertions covering all decision shapes, tool-call schemas, and hold/close action types.
- `tests/agents/test_tool_aware_gate.py` — tool-aware gate: verifies `build_hold_tool` activation and correct tool selection per scenario.
- `scripts/pr_b2_phase_a_probe.py` / `scripts/pr_b2_phase_b_probe.py` — drift-detection probes runnable locally against a live LLM key.

```bash
cd apps/backend
uv run pytest tests/agents/ -q
```

## Historical note

The 22-cassette gate (Phase 4.5 – Phase 8) used VCR cassettes synthesised deterministically from hand-curated baseline JSONs via `_cassette_synth.py`. The gate was a characterization gate (≥ 0.95 pass rate), not byte-exact parity. It was superseded because:

1. Prompt rewrite (PR-B2 Phase A) and `build_hold_tool` activation (Phase B) diverged the live LLM responses from the frozen baselines.
2. The 28 new structured tests provide a more direct, maintainable regression signal aligned with the current prompt contract.

See `.omc/plans/prompt-audit-modernization.md` §Step 7 for the full rationale.
