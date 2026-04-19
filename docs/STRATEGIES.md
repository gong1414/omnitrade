<p align="right">
  <b>English</b> | <a href="./STRATEGIES_ZH.md">简体中文</a>
</p>

# OmniTrade — Strategies (11 total)

> Canonical parameter reference for every strategy shipped with OmniTrade.
> Regression-gated by the structured output contract test suite in `tests/agents/` (PR-B2 Phase 9).
> Source enum: `apps/backend/src/omnitrade/domain/enums.py::StrategyName`.

---

## Quick reference

| # | Enum value | Activation | Prompt branch | Code-level protection | Frozen fixtures |
|---|---|---|---|---|---|
| 1 | `arena-guardian` | `TRADING_STRATEGY=arena-guardian` | full standard | off | 06, 19 |
| 2 | `arena-steward` | `TRADING_STRATEGY=arena-steward` | full standard | off | 05, 11, 18 |
| 3 | `arena-raider` | `TRADING_STRATEGY=arena-raider` | full standard | off | 07 |
| 4 | `arena-raider-squad` | `TRADING_STRATEGY=arena-raider-squad` | team sub-agents | off | 16 |
| 5 | `arena-scalper` | `TRADING_STRATEGY=arena-scalper` + `TRADING_INTERVAL_MINUTES=5` | full standard | off | 04, 08, 09, 17 |
| 6 | `arena-swingsmith` | `TRADING_STRATEGY=arena-swingsmith` + `TRADING_INTERVAL_MINUTES=20` | full standard | **on** (auto-close) | 01, 02, 03, 10, 22 |
| 7 | `arena-strider` | `TRADING_STRATEGY=arena-strider` + `TRADING_INTERVAL_MINUTES=30` | full standard | off | 20 |
| 8 | `arena-rebate-hunter` | `TRADING_STRATEGY=arena-rebate-hunter` + `TRADING_INTERVAL_MINUTES=2-3` | full standard | **on** | 12 |
| 9 | `arena-autopilot` | `TRADING_STRATEGY=arena-autopilot` | **minimal** (AI-autonomous/arena-dual-signal branch) | **on** + AI override | 13, 14 |
| 10 | `arena-tribunal` | `TRADING_STRATEGY=arena-tribunal` | jury sub-agents | off | 21 |
| 11 | `arena-dual-signal` | `TRADING_STRATEGY=arena-dual-signal` (registry fallback) | **minimal** (AI-autonomous/arena-dual-signal branch) | off | 15 |

Parity fixtures refer to files under `tests/fixtures/frozen/market_snapshots/`.
All 11 strategies are exercised at least once by the 22 frozen snapshots; aggregate parity at the Phase 4.5 gate is 22 / 22 = 1.00, with behavioural-equivalence parity ≥ 0.95.

> **Formula convention**: unless stated, leverage bands are `ceil(maxLeverage × pct)` with a per-strategy floor. `maxLeverage` defaults to `MAX_LEVERAGE=25`.
> Levels `low / mid / high` = leverage bands; stop-loss values are levered PnL %.

---

## 1. `arena-guardian` — 稳健

Low-risk scalping with tight stops and arena-raider partial take-profit at small gains.

| Param | Low | Mid | High |
|---|---|---|---|
| Leverage band | `max(2, ceil(0.1×L))` | — | `max(4, ceil(0.3×L))` |
| Stop-loss (%) | -2 | -1.5 | -1 |
| Trailing L1 / L2 / L3 | 3 → 1 | 6 → 3 | 10 → 6 |
| Partial take-profit stages (trigger%, close%) | 5, 30 | 10, 60 | 20, 100 |
| Peak drawdown protection | 15 | — | — |
| Position size | 15–25 % | | |

- **Activation:** `TRADING_STRATEGY=arena-guardian`
- **Code-level protection:** off (AI-driven closes)
- **Fixtures:** `case_06_guardian_sl_low.json`, `case_19_guardian_hold.json`

## 2. `arena-steward` — 平衡

Mid-risk default for most users.

| Param | Low | Mid | High |
|---|---|---|---|
| Leverage band | `max(3, ceil(0.3×L))` | — | `max(8, ceil(0.6×L))` |
| Stop-loss (%) | -2.5 | -2 | -1.5 |
| Trailing L1 / L2 / L3 | 5 → 2 | 10 → 5 | 20 → 12 |
| Partial take-profit (trigger%, close%) | 8, 30 | 15, 60 | 25, 100 |
| Peak drawdown protection | 20 | | |
| Position size | 20–30 % | | |

- **Activation:** `TRADING_STRATEGY=arena-steward`
- **Code-level protection:** off
- **Fixtures:** `case_05_steward_sl_mid.json`, `case_11_steward_partial_stage3.json`, `case_18_steward_open_short.json`

## 3. `arena-raider` — 激进

High-leverage single-agent mode.

| Param | Low | Mid | High |
|---|---|---|---|
| Leverage band | `max(8, ceil(0.6×L))` | — | `max(15, L)` |
| Stop-loss (%) | -3 | -2 | -1.5 |
| Trailing L1 / L2 / L3 | 4 → 1.5 | 8 → 4 | 15 → 9 |
| Partial take-profit (trigger%, close%) | 6, 40 | 12, 70 | 20, 100 |
| Peak drawdown protection | 25 | | |
| Position size | 25–35 % | | |

- **Activation:** `TRADING_STRATEGY=arena-raider`
- **Code-level protection:** off
- **Fixtures:** `case_07_raider_sl_override.json` (exercises `positions.stop_loss` override path)

## 4. `arena-raider-squad` — 激进团

Multi-agent arena-raider mode. Uses 4 sub-agents registered as
``StructuredTool`` in the think-node ``ToolRegistry`` (Phase 8.5a):

- **trendExpert**, **predictionExpert**, **moneyFlowExpert**, **riskControlExpert**

| Param | Value |
|---|---|
| Leverage band | team-led (high band) |
| Position size | 30–40 % (**requires ≥ 2 open positions**) |
| Stop-loss / trailing / partial | arena-raider band, team-coordinated |
| Peak drawdown protection | 25 |
| Code-level protection | off (team risk-control agent enforces) |

- **Status:** **implemented (opt-in via `MULTI_AGENT_ENABLED=true`)**. Default off keeps the single-agent path on the structured output contract gate.
- **Activation:** `TRADING_STRATEGY=arena-raider-squad` + `MULTI_AGENT_ENABLED=true`
- **Cost impact:** a cycle that actually invokes the 4 experts is ~2-3× the single-agent cost for the same strategy.
- **Strictness:** `MULTI_AGENT_STRICT=true` (default) — partial sub-agent failure (e.g. `trendExpert` timeout past `EXPERT_TIMEOUT_SECONDS=15`) raises `MultiAgentDegradedError` and fails the cycle. Ops can set `MULTI_AGENT_STRICT=false` for soft-degrade back to the single-agent path.
- **Prompt branch:** team sub-agent factories live in `application/multi_agent/team_experts.py`; prompts in `agents/prompts/multi_agent/`.
- **Fixtures:** `case_16_raidersquad_close.json`

## 5. `arena-scalper` — 超短线

5-minute scalping with arena-raider partial take-profit at small %.

| Param | Low | Mid | High |
|---|---|---|---|
| Leverage band | `max(3, ceil(0.5×L))` | — | `max(5, ceil(0.75×L))` |
| Stop-loss (%) | -2.5 | -2 | -1.5 |
| Trailing L1 / L2 / L3 | 4 → 1.5 | 8 → 4 | 15 → 8 |
| Partial take-profit (trigger%, close%) | 15, 50 | 25, 50 | 35, 100 |
| Peak drawdown protection | 20 | | |
| Position size | 18–25 % | | |

- **Activation:** `TRADING_STRATEGY=arena-scalper` + `TRADING_INTERVAL_MINUTES=5`
- **Code-level protection:** off
- **Fixtures:** `case_04_scalper_sl_high.json`, `case_08_scalper_partial_stage1.json`, `case_09_scalper_partial_stage2.json`, `case_17_scalper_open_only.json`

## 6. `arena-swingsmith` — 波段趋势

Wide bands designed to ride multi-day swings. **Activates code-level protection** (monitors can auto-close).

| Param | Low | Mid | High |
|---|---|---|---|
| Leverage band | `max(2, ceil(0.2×L))` | — | `max(5, ceil(0.5×L))` |
| Stop-loss (%) | -9 | -7.5 | -5.5 |
| Trailing L1 / L2 / L3 | 15 → 8 | 30 → 20 | 50 → 35 |
| Partial take-profit (trigger%, close%) | 50, 40 | 80, 60 | 120, 100 |
| Peak drawdown protection | 35 | | |
| Position size | 20–35 % | | |

- **Activation:** `TRADING_STRATEGY=arena-swingsmith` + `TRADING_INTERVAL_MINUTES=20`
- **Code-level protection:** **on** — `trailing_stop_monitor` can auto-close
- **Fixtures:** `case_01_swingsmith_trailing_L1.json`, `case_02_swingsmith_trailing_L2.json`, `case_03_swingsmith_trailing_L3.json`, `case_10_swingsmith_partial_stage1.json`, `case_22_swingsmith_trailing_edge.json`

## 7. `arena-strider` — 中长线

Low-leverage, wide-band hold strategy for trend followers.

| Param | Value |
|---|---|
| Leverage band | low |
| Stop-loss / trailing / partial | wide |
| Peak drawdown protection | 40 |
| Position size | wide |

- **Activation:** `TRADING_STRATEGY=arena-strider` + `TRADING_INTERVAL_MINUTES=30`
- **Code-level protection:** off
- **Fixtures:** `case_20_strider_hold.json`

## 8. `arena-rebate-hunter` — 返佣套利

Low-leverage, high-frequency strategy designed to maximise fee rebates. Activates code-level protection.

| Param | Value |
|---|---|
| Leverage band | low |
| Stop-loss / trailing / partial | tight |
| Peak drawdown protection | 10 |
| Position size | small |

- **Activation:** `TRADING_STRATEGY=arena-rebate-hunter` + `TRADING_INTERVAL_MINUTES=2-3`
- **Code-level protection:** **on**
- **Rebate formula:** `GET /api/account` returns `rebateAmount = totalFees × FEE_REBATE_PERCENT / 100` over a rolling 24 h window of `trades(type='close')`.
- **Fixtures:** `case_12_rebatehunter_partial_tight.json`

## 9. `arena-autopilot` — AI 自主

Fully autonomous mode — AI gets maximal latitude with code-level protection as the safety net and AI-override enabled.

| Param | Value |
|---|---|
| Leverage band | up to `MAX_LEVERAGE` |
| Stop-loss / trailing / partial | **dual protection** — code monitor auto-triggers, AI may also close early |
| Peak drawdown | auto |
| Position size | up to max |

- **Activation:** `TRADING_STRATEGY=arena-autopilot` (`.env.example` default)
- **Prompt branch:** **minimal** AI-autonomous/arena-dual-signal branch (no per-strategy prescriptive text; hard risk floor + free-form AI judgement)
- **Code-level protection:** **on** + AI override allowed
- **Fixtures:** `case_13_autopilot_close_full.json`, `case_14_autopilot_close_partial.json`

## 10. `arena-tribunal` — 陪审团

3-expert jury registered as ``StructuredTool`` in the think-node
``ToolRegistry`` (Phase 8.5a): **technicalAnalyst**, **trendAnalyst**,
**riskAssessor**.

| Param | Value |
|---|---|
| Leverage band | arena-steward band |
| Position size | arena-steward band |
| Stop-loss / trailing / partial | decided by jury consensus |
| Peak drawdown protection | — |
| Code-level protection | off |

- **Status:** **implemented (opt-in via `MULTI_AGENT_ENABLED=true`)**. Default off keeps the single-agent path on the structured output contract gate.
- **Activation:** `TRADING_STRATEGY=arena-tribunal` + `MULTI_AGENT_ENABLED=true`
- **Cost impact:** a cycle that actually invokes the 3 jurors is ~2-3× the single-agent cost for the same strategy.
- **Strictness:** `MULTI_AGENT_STRICT=true` (default) — partial juror failure raises `MultiAgentDegradedError` and fails the cycle. Ops can set `MULTI_AGENT_STRICT=false` for soft-degrade back to the single-agent path.
- **Prompt branch:** juror factories live in `application/multi_agent/consensus_jurors.py`; prompts in `agents/prompts/multi_agent/`.
- **Fixtures:** `case_21_tribunal_close_half.json`

## 11. `arena-dual-signal` — Alpha Beta

Registry-fallback default. Minimal prompt branch; simple open → hold ≤ 6 h → AI-close pattern.

| Param | Value |
|---|---|
| Leverage band | up to `MAX_LEVERAGE` |
| Stop-loss / trailing / partial | — (AI-driven) |
| `maxIdleHours` | **6** |
| Position size | up to max |

- **Activation:** `TRADING_STRATEGY=arena-dual-signal` — also the **code-level registry fallback** when `TRADING_STRATEGY` resolves to an unknown value
- **Prompt branch:** minimal AI-autonomous/arena-dual-signal branch (same as `arena-autopilot`)
- **Code-level protection:** off
- **Fixtures:** `case_15_dualsignal_close.json`

---

## Parity checklist

Every strategy below must have at least one fixture in the 22-snapshot parity set. A missing strategy would fail the Phase 7 gate (see `scripts/run_parity.py`).

- [x] `arena-guardian` — snapshot_06, snapshot_19
- [x] `arena-steward` — snapshot_05, snapshot_11, snapshot_18
- [x] `arena-raider` — snapshot_07
- [x] `arena-raider-squad` — snapshot_16
- [x] `arena-scalper` — snapshot_04, snapshot_08, snapshot_09, snapshot_17
- [x] `arena-swingsmith` — snapshot_01, snapshot_02, snapshot_03, snapshot_10, snapshot_22
- [x] `arena-strider` — snapshot_20
- [x] `arena-rebate-hunter` — snapshot_12
- [x] `arena-autopilot` — snapshot_13, snapshot_14
- [x] `arena-tribunal` — snapshot_21
- [x] `arena-dual-signal` — snapshot_15

**Aggregate coverage:** 22 / 22 fixtures, all 11 strategies present.

---

## Where to tune parameters

- Per-strategy numbers live in `apps/backend/src/omnitrade/domain/strategies/{name}.py`.
- Risk floor (`MAX_LEVERAGE`, `MAX_POSITIONS`, `MAX_HOLDING_HOURS`, `EXTREME_STOP_LOSS_PERCENT`, drawdown tiers) is in `infrastructure/config/risk_params.py`, read from env.
- Sub-agent prompts live in `agents/jury/*.py` (consensus) and `agents/team/*.py` (arena-raider-squad).
- Registry fallback logic (unknown strategy → `arena-dual-signal`) is in `domain/strategies/registry.py`.

See [ARCHITECTURE.md § Monitor Waiver](./ARCHITECTURE.md#monitor-waiver-adr) for why `arena-swingsmith` and `arena-rebate-hunter` (the two strategies with code-level protection) share the same three-way-state atomicity guarantee as every other strategy.
