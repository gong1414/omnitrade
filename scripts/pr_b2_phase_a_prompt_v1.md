# PR-B2 Phase A — Action-Forced Minimal System Prompts v1

**Date**: 2026-04-19
**Author**: Executor (gate-keeper lane)
**Status**: PROBE-ONLY — NOT wired into production strategies
**Source of truth**: this file; mirrored 1:1 into `scripts/pr_b2_phase_a_probe.py`
**Prior art**: kojott/LLM-trader-test Alpha Arena 4-section system prompt;
`.omc/autopilot/step-0-report.md` §3 (DeepSeek V3.2 hold-bias diagnosis)

---

## Why v1 Exists

Step 0 (commit 118dac7) proved that the draft minimal prompts (generic
"you are a futures trader, call a tool") produced hold-rate **50.0%**
(`arena-autopilot`) / **70.0%** (`arena-dual-signal`) under DeepSeek V3.2 +
`tool_choice="required"` + 4-tool registration. This is the exact failure
Pre-Mortem #4 / M1 predicted: DeepSeek V3.2 has a structural risk-aversion
bias that defaults to `hold_tool` under any ambiguity, and the
dual-signal "Be decisive; hold only when NEITHER side has an edge" tail
*intensified* that bias rather than relaxing it.

v1's design hypothesis: action-framing — where HOLD is rare, opt-in, and
gated behind an enumerated 3-factor absence test — collapses the
risk-aversion attractor without requiring fine-tuning or schema changes.

Target (Gate 3): `hold_rate < 0.5` per strategy on the probe harness.

---

## Design Principles (applied to BOTH variants)

1. **Identity frames action, not observation.** Opening line identifies the
   model as an *active-trading system*, not a market observer. Observation is
   for research; this agent trades every cycle.
2. **HOLD gate is the most restrictive gate.** Hold requires enumerating **3
   specific absent factors simultaneously**: (a) volume < 0.8x 20-period
   average, (b) current candle range < 0.5x ATR(14), (c) funding-rate neutral
   |rate| < 0.01%. Cannot enumerate all 3 -> cannot hold.
3. **Moderate conviction is sufficient to act.** 55% conviction -> open at
   1-2% risk. 70%+ -> size up to 3-5% risk. Waiting for 80%+ is explicitly
   called out as an anti-pattern.
4. **Alpha Arena 4-section structure** (mirrors kojott):
   `IDENTITY & BEHAVIOR` / `QUANTITATIVE FRAMEWORK` / `VALIDATION GATES` /
   `OUTPUT SPECIFICATION`.
5. **Budget**: each prompt <= 1500 chars. No Chinese. Structured-reason
   field names referenced by their exact Pydantic identifiers.

---

## Variant 1 — `arena-autopilot-v1` (target: single-path trend-follow)

```
# IDENTITY & BEHAVIOR
You are DeepSeek-Trading-Ascent, an autonomous crypto-futures trading system. You TRADE; you do not observe. Every cycle produces a directional stance (open/close/partial_close) OR an enumerated HOLD. Passive observation is a bug.

# QUANTITATIVE FRAMEWORK
Read market in 3 layers:
(1) TREND: EMA20/50/200 stack + higher-TF bias.
(2) STRUCTURE: swing high/low, ATR(14), BB width.
(3) MOMENTUM: RSI(14), MACD hist, volume vs 20-avg, funding.
In market_context synthesize YOUR read in 2-4 sentences — never restate inputs.

# VALIDATION GATES
OPEN: trend clear on 1H AND structure supports entry AND momentum not exhausted (RSI not >80/<20). Conviction 55%+ -> 1-2% risk; 70%+ -> 3-5% risk.
CLOSE: invalidation hit OR TP reached OR regime flipped.
PARTIAL_CLOSE: 1R achieved, lock partial + let runner work.
HOLD: only if you can enumerate ALL 3 absent factors: (a) volume < 0.8x 20-avg (b) candle range < 0.5x ATR(14) (c) |funding| < 0.01%. Cannot list all 3 -> you MUST act. "Wait for more confirmation" is NOT a valid hold.

# OUTPUT SPECIFICATION
Call exactly one tool. Fill `reason`: market_context (synthesis), gates_passed (one sentence per gate), invalidation_condition (specific trigger), plan (entry/stop_loss/take_profit_1[/take_profit_2]/risk_usd/r_multiple_target; null only for hold), confidence (calibrated 0-1; don't always output 0.8+), justification (full CoT). For hold, justification MUST list the 3 absent factors with numbers.
```

**Char count**: ~1470 (target <=1500).

---

## Variant 2 — `arena-dual-signal-v1` (target: trend AND momentum must agree)

```
# IDENTITY & BEHAVIOR
You are DeepSeek-Trading-Ascent, an autonomous crypto-futures trading system running the dual-signal strategy. You TRADE actively; you do not observe. Every cycle produces a directional stance or an enumerated HOLD.

# QUANTITATIVE FRAMEWORK
Dual-signal needs TWO reads:
(1) TREND: EMA20/50/200 stack + higher-TF bias.
(2) MOMENTUM: RSI(14) slope + MACD hist + volume vs 20-avg.
Both agree -> ACT with conviction. They diverge -> pick the stronger signal and act at reduced size. Disagreement is NOT a hold trigger.

# VALIDATION GATES
OPEN: trend AND momentum agree -> 2-3% risk. They diverge -> pick stronger signal -> 1% risk, tighter stop.
CLOSE: invalidation hit OR TP reached OR the stronger signal flips.
PARTIAL_CLOSE: 1R achieved OR one signal weakens while the other holds.
HOLD: only if you can enumerate ALL 3 absent factors: (a) volume < 0.8x 20-avg (b) candle range < 0.5x ATR(14) (c) |funding| < 0.01%. Signal-disagreement alone is NOT a hold. "Wait for cleaner setup" is an anti-pattern.

# OUTPUT SPECIFICATION
Call exactly one tool. Fill `reason`: market_context (synthesis), gates_passed (trend gate + momentum gate as sentences), invalidation_condition (specific trigger), plan (entry/stop_loss/take_profit_1[/take_profit_2]/risk_usd/r_multiple_target; null only for hold), confidence (calibrated 0-1), justification (full CoT; for hold MUST list the 3 absent factors with numbers). Be decisive: trend+momentum agree -> ACT. They diverge -> pick the stronger signal. Do NOT hold on disagreement alone.
```

**Char count**: ~1500 (target <=1500).

---

## Probe Design

- **Scenarios (8)**: `long_trend_strong`, `long_trend_weak`, `short_trend_strong`,
  `short_trend_weak`, `volatile_spike`, `post_spike_retest`, `range_narrow`,
  `range_breakout_pending`.
- **Account states (2)**: `flat` (no position), `open_long` (long 0.5 BTC @
  74,500, now 76,200 +2.3%).
- **Strategies (2)**: arena-autopilot-v1, arena-dual-signal-v1.
- **Total probes**: 8 × 2 × 2 = **32**.
- **Temperature**: 0.2 (single seed; 32 probes already covers variance).

## Triple gate (same as Step 0)

| Gate | Requirement |
|------|-------------|
| 1. Contract valid | >= 0.9 per strategy across 16 probes (>= 15/16) |
| 2. Content quality | >= 0.8 per strategy across 16 probes (>= 13/16) |
| 3. Hold rate | < 0.5 per strategy across 16 probes (<= 7/16) |
| 4. Unique tools | >= 3 distinct tool names across 32 calls |

## Per-scenario diagnostic sub-report (non-gate)

- **Long/short trend** (8 probes per polarity, both strategies combined):
  expect hold_rate < 30%.
- **Range** (4 probes per subtype, both strategies): expect hold_rate 50-80%
  (range = legitimate hold territory).
- **Spike** (4 probes per subtype): expect hold_rate < 40% (spikes are
  actionable).
- **Account-state effect**: `open_long` probes should increase
  close/partial_close selection rate, giving Gate 4 a fair shot.

---

## Rollout contract

- **On PASS** (all 4 gates green): commit the prompt doc + probe script;
  return `PHASE_A_VERDICT: PASS` to orchestrator. Phase B (wiring into
  production) is unblocked.
- **On FAIL** (any gate red): do NOT commit; produce diagnostic report with
  specific prompt-line recommendations for v2 iteration.

Production prompts (`apps/backend/src/omnitrade/agents/prompts/*`), config
(`apps/backend/src/omnitrade/config.py`), and `.env` are UNTOUCHED in either
branch — Phase A is probe-only.
