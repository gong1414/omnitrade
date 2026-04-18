# Flaky Quarantine — Behavioural Equivalence

Per the consensus plan §5 Phase 4.5, tests in the behavioural-equivalence
suite whose pass/fail verdict is not deterministic across ≥10 consecutive
CI runs are **quarantined** into this directory until the underlying
source of non-determinism is fixed.

## Protocol

A test qualifies as "flaky" when it satisfies BOTH:

1. **Flake rate over CI window** — over the last 10 consecutive CI runs
   on the main branch, the test has at least one pass AND at least one
   fail while the cassette, fixture, and code under test are unchanged.
2. **Rate threshold** — `fail_count / 10 ≤ 0.05` (plan §5 bullet 8).
   Any test above 5 % flake rate is a blocker; quarantining is NOT a
   substitute for fixing the root cause on such tests.

A quarantined test:

- Moves into `tests/behavioral_equivalence/flaky/` (this folder) with
  its entire file (e.g. `test_foo_flaky.py`).
- Is decorated with `@pytest.mark.flaky` (or the runner-specific
  equivalent) at the top of the module.
- Is labelled `owner:<person>` via the GitHub issue referenced below.
- Gets a tracking GitHub issue linked in the module docstring; CI fails
  if a file here has no matching open issue.

## Why this is empty in Phase 4.5

We cannot observe a 10-run CI window from a single Phase 4.5 shot. The
directory is scaffolded now so the Phase-4.5 gate and Phase-5 CI harness
can start enforcing quarantine hygiene the moment real run-to-run
variance appears. No test is currently quarantined.

## De-quarantining

A test leaves this folder when its flake rate returns to zero over the
next 10 consecutive CI runs after the fix landing. The GitHub issue is
closed in the same PR.
