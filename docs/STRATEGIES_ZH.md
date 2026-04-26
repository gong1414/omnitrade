<p align="right">
  <a href="./STRATEGIES.md">English</a> | <b>简体中文</b>
</p>

# OmniTrade —— 11 套策略

> OmniTrade 内置策略的权威参数表。
> 所有取值由 22-fixture 行为等价门锁定（Decision-equivalent 通过率 ≥ 0.95）。
> 源枚举：`apps/backend/src/omnitrade/domain/enums.py::StrategyName`。

---

## 速览

| # | 枚举值 | 激活 | Prompt 分支 | 代码级保护 | 固化 fixture |
|---|---|---|---|---|---|
| 1 | `arena-guardian` | `TRADING_STRATEGY=arena-guardian` | 完整 | 关 | 06、19 |
| 2 | `arena-steward` | `TRADING_STRATEGY=arena-steward` | 完整 | 关 | 05、11、18 |
| 3 | `arena-raider` | `TRADING_STRATEGY=arena-raider` | 完整 | 关 | 07 |
| 4 | `arena-raider-squad` | `TRADING_STRATEGY=arena-raider-squad` | team sub-agent | 关 | 16 |
| 5 | `arena-scalper` | `TRADING_STRATEGY=arena-scalper` + `TRADING_INTERVAL_MINUTES=5` | 完整 | 关 | 04、08、09、17 |
| 6 | `arena-swingsmith` | `TRADING_STRATEGY=arena-swingsmith` + `TRADING_INTERVAL_MINUTES=20` | 完整 | **开**（自动平仓） | 01、02、03、10、22 |
| 7 | `arena-strider` | `TRADING_STRATEGY=arena-strider` + `TRADING_INTERVAL_MINUTES=30` | 完整 | 关 | 20 |
| 8 | `arena-rebate-hunter` | `TRADING_STRATEGY=arena-rebate-hunter` + `TRADING_INTERVAL_MINUTES=2-3` | 完整 | **开** | 12 |
| 9 | `arena-autopilot` | `TRADING_STRATEGY=arena-autopilot` | **minimal**（autopilot / dual-signal 分支） | **开** + AI 覆盖 | 13、14 |
| 10 | `arena-tribunal` | `TRADING_STRATEGY=arena-tribunal` | jury sub-agent | 关 | 21 |
| 11 | `arena-dual-signal` | `TRADING_STRATEGY=arena-dual-signal`（注册表 fallback） | **minimal**（autopilot / dual-signal 分支） | 关 | 15 |

Fixture 编号指 `tests/fixtures/frozen/market_snapshots/` 下的 22 份。11 套策略每个都至少被一份 fixture 覆盖；总体通过率 ≥ 0.95。

> **公式约定**：未特别说明时，杠杆带 = `ceil(maxLeverage × pct)` 再配上每套策略的下限。`maxLeverage` 默认 `MAX_LEVERAGE=25`。
> `low / mid / high` 指杠杆带；止损值是杠杆化 PnL %。

---

## 1. `arena-guardian` —— 稳健

低风险、小止损、小盈利就落袋的高频短线。

| 参数 | Low | Mid | High |
|---|---|---|---|
| 杠杆带 | `max(2, ceil(0.1×L))` | — | `max(4, ceil(0.3×L))` |
| 止损 (%) | -2 | -1.5 | -1 |
| 移动止损 L1 / L2 / L3 | 3 → 1 | 6 → 3 | 10 → 6 |
| 分批止盈 stage（trigger%, close%） | 5, 30 | 10, 60 | 20, 100 |
| 峰值回撤保护 | 15 | — | — |
| 仓位大小 | 15–25 % | | |

- **激活：** `TRADING_STRATEGY=arena-guardian`
- **代码级保护：** 关（AI 驱动平仓）
- **Fixture：** `case_06_guardian_sl_low.json`、`case_19_guardian_hold.json`

## 2. `arena-steward` —— 平衡

多数用户的默认中风险策略。

| 参数 | Low | Mid | High |
|---|---|---|---|
| 杠杆带 | `max(3, ceil(0.3×L))` | — | `max(8, ceil(0.6×L))` |
| 止损 (%) | -2.5 | -2 | -1.5 |
| 移动止损 L1 / L2 / L3 | 5 → 2 | 10 → 5 | 20 → 12 |
| 分批止盈（trigger%, close%） | 8, 30 | 15, 60 | 25, 100 |
| 峰值回撤保护 | 20 | | |
| 仓位大小 | 20–30 % | | |

- **激活：** `TRADING_STRATEGY=arena-steward`
- **代码级保护：** 关
- **Fixture：** `case_05_steward_sl_mid.json`、`case_11_steward_partial_stage3.json`、`case_18_steward_open_short.json`

## 3. `arena-raider` —— 激进

高杠杆单智能体模式。

| 参数 | Low | Mid | High |
|---|---|---|---|
| 杠杆带 | `max(8, ceil(0.6×L))` | — | `max(15, L)` |
| 止损 (%) | -3 | -2 | -1.5 |
| 移动止损 L1 / L2 / L3 | 4 → 1.5 | 8 → 4 | 15 → 9 |
| 分批止盈（trigger%, close%） | 6, 40 | 12, 70 | 20, 100 |
| 峰值回撤保护 | 25 | | |
| 仓位大小 | 25–35 % | | |

- **激活：** `TRADING_STRATEGY=arena-raider`
- **代码级保护：** 关
- **Fixture：** `case_07_raider_sl_override.json`（演练 `positions.stop_loss` 覆盖路径）

## 4. `arena-raider-squad` —— 激进团

多智能体进攻模式。由 `agents/experts_team.build_agno_team` 构造的咨询
Agno `Team` 提供建议（受 `MULTI_AGENT_ENABLED=true` 控制），4 个成员：

- **trendExpert**、**predictionExpert**、**moneyFlowExpert**、**riskControlExpert**

Team 的裁决文本会注入到主 Agno Agent 的 prompt 作为咨询上下文，最终
`Decision` 仍由主 Agent 通过 DecisionRecorder 工具调用产出。

| 参数 | 值 |
|---|---|
| 杠杆带 | 团队主导（high band） |
| 仓位大小 | 30–40 %（**要求 ≥ 2 个开仓**） |
| 止损 / 移动 / 分批 | arena-raider 带，团队协调 |
| 峰值回撤保护 | 25 |
| 代码级保护 | 关（由团队 risk-control agent 执行） |

- **状态：** **已实现（通过 `MULTI_AGENT_ENABLED=true` opt-in）**。默认关闭以保持单智能体路径对 22/22 行为等价门 byte-exact。
- **激活：** `TRADING_STRATEGY=arena-raider-squad` + `MULTI_AGENT_ENABLED=true`
- **成本影响：** 真正调用 4 个专家的周期约为单智能体策略的 2-3×。
- **严格度：** `MULTI_AGENT_STRICT=true`（默认）—— 子 Agent 局部失败（例如 `trendExpert` 超过 `EXPERT_TIMEOUT_SECONDS=15`）抛 `MultiAgentDegradedError` 使周期失败。运维可设 `MULTI_AGENT_STRICT=false` 软降级回单智能体路径。
- **Prompt 分支：** team 子 agent 工厂在 `application/multi_agent/team_experts.py`；prompt 在 `agents/prompts/multi_agent/`。
- **Fixture：** `case_16_raidersquad_close.json`

## 5. `arena-scalper` —— 超短线

5 分钟 scalping，带激进分批止盈。

| 参数 | Low | Mid | High |
|---|---|---|---|
| 杠杆带 | `max(3, ceil(0.5×L))` | — | `max(5, ceil(0.75×L))` |
| 止损 (%) | -2.5 | -2 | -1.5 |
| 移动止损 L1 / L2 / L3 | 4 → 1.5 | 8 → 4 | 15 → 8 |
| 分批止盈（trigger%, close%） | 15, 50 | 25, 50 | 35, 100 |
| 峰值回撤保护 | 20 | | |
| 仓位大小 | 18–25 % | | |

- **激活：** `TRADING_STRATEGY=arena-scalper` + `TRADING_INTERVAL_MINUTES=5`
- **代码级保护：** 关
- **Fixture：** `case_04_scalper_sl_high.json`、`case_08_scalper_partial_stage1.json`、`case_09_scalper_partial_stage2.json`、`case_17_scalper_open_only.json`

## 6. `arena-swingsmith` —— 波段趋势

宽带，追多日波动。**启用代码级保护**（monitor 可自动平仓）。

| 参数 | Low | Mid | High |
|---|---|---|---|
| 杠杆带 | `max(2, ceil(0.2×L))` | — | `max(5, ceil(0.5×L))` |
| 止损 (%) | -9 | -7.5 | -5.5 |
| 移动止损 L1 / L2 / L3 | 15 → 8 | 30 → 20 | 50 → 35 |
| 分批止盈（trigger%, close%） | 50, 40 | 80, 60 | 120, 100 |
| 峰值回撤保护 | 35 | | |
| 仓位大小 | 20–35 % | | |

- **激活：** `TRADING_STRATEGY=arena-swingsmith` + `TRADING_INTERVAL_MINUTES=20`
- **代码级保护：** **开** —— `trailing_stop_monitor` 可自动平仓
- **Fixture：** `case_01_swingsmith_trailing_L1.json`、`case_02_swingsmith_trailing_L2.json`、`case_03_swingsmith_trailing_L3.json`、`case_10_swingsmith_partial_stage1.json`、`case_22_swingsmith_trailing_edge.json`

## 7. `arena-strider` —— 中长线

低杠杆、宽带持有策略，适合趋势跟随。

| 参数 | 值 |
|---|---|
| 杠杆带 | low |
| 止损 / 移动 / 分批 | 宽 |
| 峰值回撤保护 | 40 |
| 仓位大小 | 宽 |

- **激活：** `TRADING_STRATEGY=arena-strider` + `TRADING_INTERVAL_MINUTES=30`
- **代码级保护：** 关
- **Fixture：** `case_20_strider_hold.json`

## 8. `arena-rebate-hunter` —— 返佣套利

低杠杆、高频率，以吃返佣为目标。启用代码级保护。

| 参数 | 值 |
|---|---|
| 杠杆带 | low |
| 止损 / 移动 / 分批 | 紧 |
| 峰值回撤保护 | 10 |
| 仓位大小 | 小 |

- **激活：** `TRADING_STRATEGY=arena-rebate-hunter` + `TRADING_INTERVAL_MINUTES=2-3`
- **代码级保护：** **开**
- **返佣公式：** `GET /api/account` 返回 `rebateAmount = totalFees × FEE_REBATE_PERCENT / 100`，对 `trades(type='close')` 做 24 小时滚动窗口。
- **Fixture：** `case_12_rebatehunter_partial_tight.json`

## 9. `arena-autopilot` —— AI 自主

完全自主模式 —— AI 获得最大自由度；代码级保护作为安全网且允许 AI 覆盖。

| 参数 | 值 |
|---|---|
| 杠杆带 | 最高到 `MAX_LEVERAGE` |
| 止损 / 移动 / 分批 | **双保护** —— 代码 monitor 自动触发，AI 也可提前平仓 |
| 峰值回撤 | auto |
| 仓位大小 | 到上限 |

- **激活：** `TRADING_STRATEGY=arena-autopilot`（`.env.example` 默认）
- **Prompt 分支：** **minimal**（autopilot / dual-signal 分支；不给策略性硬规则；只留 hard risk 底线 + 自由 AI 判断）
- **代码级保护：** **开** + 允许 AI 覆盖
- **Fixture：** `case_13_autopilot_close_full.json`、`case_14_autopilot_close_partial.json`

## 10. `arena-tribunal` —— 陪审团

3 专家陪审团，由 `agents/experts_team.build_agno_team` 构造的咨询 Agno
`Team` 提供建议（受 `MULTI_AGENT_ENABLED=true` 控制）：
**technicalAnalyst**、**trendAnalyst**、**riskAssessor**。Team 的裁决
仅作为咨询注入主 Agent prompt，最终 `Decision` 仍由主 Agent 产出。

| 参数 | 值 |
|---|---|
| 杠杆带 | arena-steward 带 |
| 仓位大小 | arena-steward 带 |
| 止损 / 移动 / 分批 | 由陪审团共识决定 |
| 峰值回撤保护 | — |
| 代码级保护 | 关 |

- **状态：** **已实现（通过 `MULTI_AGENT_ENABLED=true` opt-in）**。默认关闭以保持单智能体路径对 22/22 行为等价门 byte-exact。
- **激活：** `TRADING_STRATEGY=arena-tribunal` + `MULTI_AGENT_ENABLED=true`
- **成本影响：** 真正调用 3 个陪审员的周期约 2-3× 单智能体成本。
- **严格度：** `MULTI_AGENT_STRICT=true`（默认）—— 局部失败抛 `MultiAgentDegradedError`。可设 `false` 软降级。
- **Prompt 分支：** juror 工厂在 `application/multi_agent/consensus_jurors.py`；prompt 在 `agents/prompts/multi_agent/`。
- **Fixture：** `case_21_tribunal_close_half.json`

## 11. `arena-dual-signal` —— Alpha-Beta

注册表 fallback 默认。Minimal prompt 分支；简单的开仓 → 持有 ≤ 6 小时 → AI 平仓模式。

| 参数 | 值 |
|---|---|
| 杠杆带 | 最高到 `MAX_LEVERAGE` |
| 止损 / 移动 / 分批 | — （AI 驱动） |
| `maxIdleHours` | **6** |
| 仓位大小 | 到上限 |

- **激活：** `TRADING_STRATEGY=arena-dual-signal` —— 也是**注册表 fallback**：`TRADING_STRATEGY` 解析到未知值时落回这里
- **Prompt 分支：** minimal autopilot / dual-signal 分支（与 `arena-autopilot` 同款）
- **代码级保护：** 关
- **Fixture：** `case_15_dualsignal_close.json`

---

## Fixture 覆盖 checklist

每套策略都必须在 22 份行为等价 fixture 里至少出现一次。缺一即行为等价门失败。

- [x] `arena-guardian` —— case_06、case_19
- [x] `arena-steward` —— case_05、case_11、case_18
- [x] `arena-raider` —— case_07
- [x] `arena-raider-squad` —— case_16
- [x] `arena-scalper` —— case_04、case_08、case_09、case_17
- [x] `arena-swingsmith` —— case_01、case_02、case_03、case_10、case_22
- [x] `arena-strider` —— case_20
- [x] `arena-rebate-hunter` —— case_12
- [x] `arena-autopilot` —— case_13、case_14
- [x] `arena-tribunal` —— case_21
- [x] `arena-dual-signal` —— case_15

**总覆盖：** 22 / 22 fixture，11 套策略全部在列。

---

## 参数调整位置

- 每套策略的具体数值在 `apps/backend/src/omnitrade/domain/strategies/{name}.py`。
- 风险底线（`MAX_LEVERAGE`、`MAX_POSITIONS`、`MAX_HOLDING_HOURS`、`EXTREME_STOP_LOSS_PERCENT`、回撤梯度）在 `infrastructure/config/risk_params.py`，从环境变量读。
- 子 Agent 的 prompt 在 `agents/jury/*.py`（陪审团）和 `agents/team/*.py`（arena-raider-squad）。
- 注册表 fallback 逻辑（未知 strategy → `arena-dual-signal`）在 `domain/strategies/registry.py`。

详情见 [ARCHITECTURE_ZH.md § 监控器豁免](./ARCHITECTURE_ZH.md#监控器豁免adr)。
