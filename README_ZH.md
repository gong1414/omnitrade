<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

<p align="center">
  <a href="https://github.com/gong1414/omnitrade"><img src="assets/logo-horizontal.svg" alt="OmniTrade" width="520"></a>
</p>

<h1 align="center">OmniTrade：大模型驱动的合约竞技场</h1>

<p align="center">
  <b>11 套策略同场竞技 · 4 条 close-path 分类 · 三位一体原子状态 · 实时仪表盘</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-Next.js%2014-000000?style=flat&logo=next.js&logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/Agent-Agno%20%2B%20AgentOS-8A2BE2?style=flat" alt="Agno">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=flat" alt="License"></a>
  <br>
  <img src="https://img.shields.io/badge/策略-11-FF6B6B" alt="Strategies">
  <img src="https://img.shields.io/badge/Close_Paths-4%2B1-4ECDC4" alt="Close Paths">
  <img src="https://img.shields.io/badge/固化_fixture-22%2F22-FFD93D" alt="Fixtures">
  <img src="https://img.shields.io/badge/测试-702_绿-2BB673" alt="Tests">
  <img src="https://img.shields.io/badge/交易所-Gate%20%2B%20OKX-F6465D" alt="Exchanges">
  <br>
  <a href="https://github.com/gong1414/omnitrade/stargazers"><img src="https://img.shields.io/github/stars/gong1414/omnitrade?style=flat&logo=github&color=FFD43B" alt="GitHub stars"></a>
  <a href="https://github.com/gong1414/omnitrade/network/members"><img src="https://img.shields.io/github/forks/gong1414/omnitrade?style=flat&logo=github&color=4F8BC9" alt="GitHub forks"></a>
  <a href="https://github.com/gong1414/omnitrade/issues"><img src="https://img.shields.io/github/issues/gong1414/omnitrade?style=flat&logo=github&color=FF6B6B" alt="GitHub issues"></a>
  <a href="https://github.com/gong1414/omnitrade/releases/latest"><img src="https://img.shields.io/github/v/release/gong1414/omnitrade?style=flat&logo=github&include_prereleases&color=8A2BE2" alt="GitHub release"></a>
  <a href="https://github.com/gong1414/omnitrade/commits/main"><img src="https://img.shields.io/github/last-commit/gong1414/omnitrade?style=flat&logo=github&color=2BB673" alt="last commit"></a>
  <a href="https://codecov.io/gh/gong1414/omnitrade"><img src="https://img.shields.io/codecov/c/github/gong1414/omnitrade?style=flat&logo=codecov" alt="Codecov"></a>
  <a href="https://securityscorecards.dev/viewer/?uri=github.com/gong1414/omnitrade"><img src="https://api.securityscorecards.dev/projects/github.com/gong1414/omnitrade/badge" alt="OpenSSF Scorecard"></a>
</p>

<p align="center">
  <a href="#-更新动态">更新</a> &nbsp;&middot;&nbsp;
  <a href="#-2-分钟跑起来">2 分钟跑</a> &nbsp;&middot;&nbsp;
  <a href="#-核心特性">特性</a> &nbsp;&middot;&nbsp;
  <a href="#-11-套策略">策略</a> &nbsp;&middot;&nbsp;
  <a href="#%EF%B8%8F-omnitrade-vs-自己手搓">vs 手搓</a> &nbsp;&middot;&nbsp;
  <a href="#-快速开始">快速开始</a> &nbsp;&middot;&nbsp;
  <a href="#-架构">架构</a> &nbsp;&middot;&nbsp;
  <a href="#-api-端点">API</a> &nbsp;&middot;&nbsp;
  <a href="#-赞助--支持本项目">赞助</a> &nbsp;&middot;&nbsp;
  <a href="#-许可证">许可证</a>
</p>

---

## 📢 项目状态

OmniTrade **持续开发中**。架构、API、策略都会随着实际运营反馈不断演进——
欢迎随时提 issue 与新需求，每一条都会被认真当回事。

如果你遇到任何问题、觉得哪里不顺手，或者想要某个新策略 / 数据源 / 仪表盘
组件，请直接 [开 issue][issues] 或 PR——具体协作流程见
[CONTRIBUTING.md](CONTRIBUTING.md)，安全漏洞请走
[SECURITY.md](SECURITY.md) 的私有上报通道。觉得项目有用的话，欢迎点
Star 关注后续进展。

[issues]: https://github.com/gong1414/omnitrade/issues

---

## ⚠️ 风险提示 — 运行前请仔细阅读

OmniTrade 会在加密货币交易所执行真实交易。合约本身是高杠杆品种，一个错误的
周期就可能让账户全亏。本项目是 MIT 协议下发布的研究型软件，**不附带任何形式
的担保**；维护者不是投资顾问，对你运行本软件造成的任何损失不承担责任。

使用本软件即代表你接受：

- **每一笔交易最终责任在你**。Agent 会自主开仓、定仓位、平仓，请把它的每一
  个决策当作你自己的决策来对待。
- **先在 testnet 跑**。`GATE_USE_TESTNET=true` 和 `OKX_USE_TESTNET=true` 是默认
  值；在切到 mainnet 之前请连续在 testnet 跑数周。
- **mainnet 先小额**。第一次实盘只放你能承受全亏的金额。HITL 大单审批
  (`HITL_OPEN_SIZE_THRESHOLD_USD`，默认 1 万美元) 是兜底，不是仓位上限的替代。
- **API Key 权限收紧**。Gate.io / OKX 上把 API key 设置成「仅交易，不允许提
  现」；交易所账户开启 2FA。
- **持续盯**。仪表盘会渲染每一个周期的推理、持仓、各 gate 状态。读它。G5
  故障短语扫描器会自动标出明显问题，但更隐蔽的问题需要人工把关。
- **合规自担**。在你所在司法管辖区内，对加密合约进行算法化交易可能受限或被
  禁止 — 运行本软件前请确认本地法规。

如果你不能接受这些前提，请到此为止。

---

## 📰 更新动态

- **2026-04-26** 🎉 **开源 `v0.1.0` 发布** — Agno 切换（Stage A–E）+ T1–T10 加固全部绿。详细 release notes：[v0.1.0](https://github.com/gong1414/omnitrade/releases/tag/v0.1.0)
- **2026-04-26** 🛡️ **OSS 质量批次** — Dependabot + CodeQL 安全扫描、main 分支保护、GitHub Pages 上线 [docs](https://gong1414.github.io/omnitrade/)、ADR 集合在 [`docs/adr/`](docs/adr/)
- **2026-04-26** 📚 **Quickstart + FAQ** — 5 分钟从 `git clone` 跑通第一个 cycle：[`docs/QUICKSTART.md`](docs/QUICKSTART.md)；11 个常见错误兜底：[`docs/FAQ.md`](docs/FAQ.md)
- **2026-04-26** 🤖 **T10 — Trade-journal RAG** — 每个 cycle 的结构化推理自动落到 `ai.trade_journal`（PgVector 混合检索），下一周期会把语义相关的历史决策注入系统提示。默认本地 `BAAI/bge-small-en-v1.5` embedder（无需 API key）
- **2026-04-26** 🛑 **T9 — HITL 大单审批** — 美元名义价值超过 `HITL_OPEN_SIZE_THRESHOLD_USD`（默认 1 万）的开仓会通过 SSE 暂停，必须由操作员在仪表盘上批准
- **2026-04-26** 🔭 **T4 — OpenTelemetry 追踪** — 每一次 Agno run / model call / tool call 都通过 OpenInference `AgnoInstrumentor` 发出 span；访问 `GET /traces` 查看每周期的调用树

---

## ⚡ 2 分钟跑起来

从 `git clone` 到「Agent 在 Gate.io testnet 上自动交易」的最短路径，一段命令贴完事：

```bash
git clone https://github.com/gong1414/omnitrade.git && cd omnitrade && \
  cp apps/backend/.env.example .env && \
  echo "现在编辑 .env：填入 LLM_API_KEY (DeepSeek)、GATE_API_KEY、GATE_API_SECRET" && \
  docker compose up -d && \
  curl -X POST http://localhost:8000/api/v1/cycle/trigger
```

之后打开 `http://localhost:3000/dashboard`。完整步骤见
[`docs/QUICKSTART.md`](docs/QUICKSTART.md)；常见错误兜底见
[`docs/FAQ.md`](docs/FAQ.md)。

---

## 💡 项目简介

OmniTrade 是一个自动化**合约期货竞技场**，11 套由大模型驱动的策略在 Gate.io / OKX 永续合约上竞逐 PnL。指向 testnet、选一个策略，就能看 Agent 分析行情、开仓、管理风险——每一个决策都能通过 22-fixture 行为等价门验证。

### 主要能力

- **11 套具名策略** —— 从 `arena-guardian`（保本型）、`arena-raider-squad`（四专家进攻队）到 `arena-autopilot`（全自主 LLM）
- **4 条 close-path 分类** —— `stop_loss` / `trailing_stop` / `partial_profit` / `ai_decision`，外加 `none`；由纯分类器 + 3 个 10 秒监控器强制执行
- **三位一体原子状态** —— `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` 在单条 SQL `UPDATE` 内落盘，止损监控器永远看不到 torn write
- **默认 testnet** —— `GATE_USE_TESTNET=true` / `OKX_USE_TESTNET=true` 开箱即用；实盘必须显式改写
- **行为等价门** —— 22 份固化 fixture 以 ≥ 0.95 的 Decision-equivalent 通过率确定性重放
- **实时仪表盘** —— Next.js 14 App Router + SWR + Server-Sent Events（EventSource），自带指数退避重连

---

## 🎯 适合谁

- **LLM Agent 研究者**：想要一个非玩具级 benchmark —— 真实交易所 API、成本压力下的结构化 tool-calling、单 PnL 驱动循环上的多智能体协作
- **量化爱好者**：把「AI 管期货」当兴趣项目，想要一套现成的全栈来玩，而不是从零搭起
- **Testnet 操作员**：想长期观察 LLM 在真实行情下的行为，再决定要不要碰 mainnet
- **MCP 工具开发者**：想看一个 `MultiMCPTools` 驱动 15 个工具（9 交易 + 6 加密数据）跑在 Agno 下的完整范例

OmniTrade **不适合**：想要现成印钞机的人、找跟单信号服务的交易者、亏不起账户余额的人。

## 🔬 使用场景

- **纸面交易 LLM**：在 Gate.io / OKX testnet 上跑数周，每个 cycle 的推理都读一遍，培养「模型到底懂什么」的直觉
- **策略对比**：同一段行情分别跑 `arena-guardian` / `arena-raider` / `arena-tribunal`，看不同 prompt 分支如何应对相同 setup
- **测试新 MCP 工具**：在 `infrastructure/mcp/` 里加一个新 FastMCP server，通过 `MultiMCPTools` 注册，看 agent 如何发现并调用
- **压测 agent 可靠性**：T7 ReliabilityEval + T8 AccuracyEval 专门盯「agent 是真用工具，还是凭记忆瞎答」这条轴
- **个人 mainnet 实盘**：testnet 跑数周 + 自己有把握之后再考虑。把它当一个需要监督的同事看待，不是自动驾驶

## ⚖️ OmniTrade vs 自己手搓

| 自己手搓的常见做法 | OmniTrade |
|---|---|
| Jupyter notebook 跑 LLM + 另一个 notebook 跑 ccxt + 一份 Postgres dump 当历史记录 | 单进程 FastAPI + AgentOS scheduler + Postgres + pgvector + 6 个监控器，`docker compose up` 起 |
| Mock 测试全过，生产迁移挂了 | 22 份固化 fixture 重放 ≥ 0.95 + 集成测试打真 SQLite/Postgres（不 mock DB） |
| LLM 幻觉持仓，下个月账单才发现 | G6 跨源一致性检查 + G5 故障短语 post_hook；幻觉持仓让 build 红，不是让钱包红 |
| 止损 / 分批平仓竞态把仓位状态搞乱 | 三位一体原子写契约 —— `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` 同一条 SQL UPDATE 落盘 |
| 没人盯的时候大单意外开了出去 | T9 HITL gate：超过 `HITL_OPEN_SIZE_THRESHOLD_USD`（默认 1 万美元）的开仓会通过 SSE 暂停，等操作员在仪表盘批准 |
| 上一轮 LLM 推理的内容下一轮就忘了 | T10 trade-journal RAG：每个决策落到 PgVector；下一轮 cycle 的系统提示里自动塞进语义相关的历史决策 |
| 不知道「agent 到底用没用工具」 | OpenTelemetry 追踪（T4）—— 每一次 Agent.arun / model call / tool call 一个 span，AgentOS `GET /traces` 服务出去 |
| 多框架漂移（LangChain + LiteLLM + LangGraph + mcp2py） | 一个框架，Agno 2.x。CI 的 Acceptance 4 强制零 legacy import |

---

## ✨ 核心特性

<table width="100%">
  <tr>
    <td align="center" width="25%" valign="top">
      <h3>🎯 策略竞技场</h3>
      <img src="https://img.shields.io/badge/11_套策略-FF6B6B?style=for-the-badge" alt="Strategies"/><br><br>
      <div align="left">
        • 11 套跨 3 档风险偏好的具名策略<br>
        • 2 条 Prompt 分支：minimal（autopilot / dual-signal）vs 完整"世界顶级交易员"<br>
        • 每套策略独立杠杆带 / 移动止损阶梯 / 分批止盈<br>
        • 多智能体模式：<code>arena-tribunal</code>（3 专家陪审团）&amp; <code>arena-raider-squad</code>（4 专家团队）
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🛡️ close-path 分类器</h3>
      <img src="https://img.shields.io/badge/4%2B1_桶-4ECDC4?style=for-the-badge" alt="Buckets"/><br><br>
      <div align="left">
        • 纯分类器：<code>close_path_classifier.py</code><br>
        • 10 秒监控器：trailing-stop / stop-loss / partial-profit<br>
        • AI 主动平仓：<code>close_position</code> / <code>partial_close</code> 工具<br>
        • 每次平仓原子写入三位一体状态
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🔌 交易所适配器</h3>
      <img src="https://img.shields.io/badge/Gate%20%2B%20OKX-FFD93D?style=for-the-badge" alt="Exchange"/><br><br>
      <div align="left">
        • ccxt 统一封装，默认 testnet<br>
        • REST: ticker / OHLCV / orderbook / openInterest / funding<br>
        • Server-Sent Events 实时仪表盘（单一推流通道）<br>
        • 订单全生命周期：开 / 平 / 分批 / 撤单
      </div>
    </td>
    <td align="center" width="25%" valign="top">
      <h3>🧪 行为等价门</h3>
      <img src="https://img.shields.io/badge/22%2F22_固化-C77DFF?style=for-the-badge" alt="Gate"/><br><br>
      <div align="left">
        • 22 份手工策展的决策契约<br>
        • VCR cassette 确定性合成<br>
        • Decision-equivalent 重放通过率 ≥ 0.95<br>
        • 每个 close-path 桶 ≥ 0.95，drift ≤ 0.05
      </div>
    </td>
  </tr>
</table>

---

## 🎯 11 套策略

每套策略都是一个具体的配置：**杠杆带 → 移动止损阶梯 → 分批止盈 stage → 止损覆盖 → 系统 Prompt 分支**。

11 个策略名速览：`arena-guardian` / `arena-steward` / `arena-raider` / `arena-raider-squad` / `arena-scalper` / `arena-swingsmith` / `arena-strider` / `arena-rebate-hunter` / `arena-autopilot` / `arena-tribunal` / `arena-dual-signal`。

<details>
<summary><b>展开看 11 套策略完整对照表</b></summary>

| # | 枚举值 | 定位 | Prompt 分支 | 代码级保护 | 对应 fixture |
|---|---|---|---|---|---|
| 1 | `arena-guardian` | 稳健保本 | 完整 | 关 | `case_06`、`case_19` |
| 2 | `arena-steward` | 默认平衡 | 完整 | 关 | `case_05`、`case_11`、`case_18` |
| 3 | `arena-raider` | 高杠杆单智能体 | 完整 | 关 | `case_07` |
| 4 | `arena-raider-squad` | 4 专家进攻团队 | team | 关 | `case_16` |
| 5 | `arena-scalper` | 5 分钟高频 | 完整 | 关 | `case_04`、`case_08`、`case_09`、`case_17` |
| 6 | `arena-swingsmith` | 波段趋势 | 完整 | **开**（自动平仓） | `case_01`-`03`、`case_10`、`case_22` |
| 7 | `arena-strider` | 中长线趋势跟随 | 完整 | 关 | `case_20` |
| 8 | `arena-rebate-hunter` | 高频返佣套利 | 完整 | **开** | `case_12` |
| 9 | `arena-autopilot` | 全自主 LLM | **minimal** | **开** + AI 覆盖 | `case_13`、`case_14` |
| 10 | `arena-tribunal` | 3 专家陪审团 | jury | 关 | `case_21` |
| 11 | `arena-dual-signal` | 注册表 fallback（未知策略 → dual-signal） | **minimal** | 关 | `case_15` |

</details>

完整参数表：[docs/STRATEGIES_ZH.md](./docs/STRATEGIES_ZH.md)。

---

## 🛡️ Close-Path 分类

四条互斥的 close path 加上 `none`。前三条由监控器驱动，`ai_decision` 由 think-node 驱动。

| Path | 驱动 | 写入 |
|---|---|---|
| `stop_loss` | `stop_loss_monitor`（10 秒） | `trades(type=close)`、`agent_decisions(trigger=stop_loss)`、删除仓位 |
| `trailing_stop` | `trailing_stop_monitor`（10 秒，`enable_code_level_protection` 时） | `trades`、`agent_decisions`、删除仓位 |
| `partial_profit` | `partial_profit_monitor`（10 秒） | 部分 `trades`、原子三位一体 `UPDATE positions`、`agent_decisions` |
| `ai_decision` | `close_position` / `partial_close` 工具（trading loop） | `trades`、原子三位一体 `UPDATE positions` |
| `none` | — | 只开仓或 hold |

完整规则 + 真值表：[`apps/backend/src/omnitrade/domain/services/close_path_classifier.py`](./apps/backend/src/omnitrade/domain/services/close_path_classifier.py)。

---

## 🚀 快速开始

### 方案 A · Docker（零配置）

```bash
cp apps/backend/.env.example .env
# 编辑 .env —— 填 LLM_API_KEY（DeepSeek）、GATE_API_KEY / OKX_API_KEY，testnet 开关保持开
docker compose up -d
# `db-init` 会自动执行 `alembic upgrade head`，backend 上线前会等它
# `service_completed_successfully`，所以无需手动迁移。
```

启动后验证一下端到端 cycle 是否真的在跑：

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger          # ≤60s 内应返回 {"status":"ok"}
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq    # 最近一条决策 JSON
```

| URL | 用途 |
|---|---|
| `http://localhost:3000/dashboard` | Next.js 仪表盘 |
| `http://localhost:8000/docs` | FastAPI 交互文档 |
| `http://localhost:8000/sse/stream` | Server-Sent Events 流（decision / position / run-paused） |

### 方案 B · 本地开发（Python 3.11 + Node 20）

```bash
# 后端
cd apps/backend
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn omnitrade.api.app:create_app --factory --reload

# 前端（新开一个终端）
cd apps/frontend
npm install
npm run dev
```

### 方案 C · 生产部署

```bash
cp .env.production.example .env.production
# 填入 secret —— 切勿 git commit .env.production
docker compose -f docker-compose.prod.yml up -d
```

完整发布清单（冒烟测试、可观测性、回滚）：[docs/RELEASE_CHECKLIST.md](./docs/RELEASE_CHECKLIST.md)。

### 前置条件

- **LLM API key** —— DeepSeek（默认 `deepseek-reasoner`，可切 `deepseek-v4-pro` / `-flash`），由 Agno 的 DeepSeek 模型类直连。
- **交易所凭证** —— Gate.io 或 OKX；**建议先 testnet**
- 方案 B 需要 Python 3.11+ 和 [`uv`](https://github.com/astral-sh/uv)
- 方案 A / C 需要 Docker + Docker Compose

---

## 🧠 环境变量

所有配置通过环境变量。两个必填，剩下都在文件里有内联注释：

- `LLM_API_KEY` —— 你的 DeepSeek / OpenAI / OpenRouter key
- `GATE_API_KEY` + `GATE_API_SECRET` —— 交易所凭证（默认 testnet）

完整 40+ 变量参考 [`apps/backend/.env.example`](./apps/backend/.env.example)，每行都有注释。

<details>
<summary><b>展开看常问的变量（默认值）</b></summary>

| 变量 | 默认 | 说明 |
|---|---|---|
| `TRADING_STRATEGY` | `arena-autopilot` | 11 套策略任选 |
| `TRADING_INTERVAL_MINUTES` | `20` | 主交易 loop 的 cron 周期 |
| `MAX_LEVERAGE` | `25` | 单仓杠杆硬上限 |
| `MAX_POSITIONS` | `5` | 并行持仓数上限 |
| `MAX_HOLDING_HOURS` | `36` | 超时强制平仓 |
| `EXTREME_STOP_LOSS_PERCENT` | `-30` | 极限止损硬地板 |
| `EXCHANGE` | `gate` | `gate` 或 `okx` |
| `GATE_USE_TESTNET` / `OKX_USE_TESTNET` | `true` | **默认 testnet，实盘必须显式改 `false`** |
| `LLM_PROVIDER` | `deepseek` | Agno DeepSeek provider key |
| `LLM_MODEL_NAME` | `deepseek/deepseek-v3.2-exp` | 任意 OpenAI 兼容模型 |
| `MULTI_AGENT_ENABLED` | `false` | 启用 `arena-raider-squad` / `arena-tribunal` |
| `FEE_REBATE_PERCENT` | `20` | 在 `/api/account` 显示为 `rebateAmount` |
| `HITL_OPEN_SIZE_THRESHOLD_USD` | `10000` | T9 —— 超过此美元名义价值的开仓暂停等批准 |
| `EMBEDDER_PROVIDER` | `fastembed` | `fastembed`（本地，默认）或 `openai` |
| `OTEL_TRACING_ENABLED` | `true` | T4 —— OpenTelemetry span 发射 |

</details>

<details>
<summary><b>推荐模型选型表</b></summary>

OmniTrade 是**重工具调用**的 Agent——开 / 平 / 分批的每一个决策都走 OpenAI 风格 tool call。模型选得好不好，直接决定 Agent 是**真的用工具**，还是**凭记忆编造答案**。

| 级别 | 例子 | 使用场景 |
|---|---|---|
| **最佳** | `anthropic/claude-sonnet-4.6`、`openai/gpt-5.4`、`google/gemini-3.1-pro` | 多智能体（`arena-raider-squad`、`arena-tribunal`）、长时研究 |
| **性价比首选**（默认） | `deepseek/deepseek-v3.2-exp`、`x-ai/grok-4`、`z-ai/glm-5`、`moonshotai/kimi-k2`、`qwen3-max` | 日常驱动——可靠的 tool-calling，只要 1/10 的成本 |
| **避免** | `*-nano`、`*-flash-lite`、蒸馏小模型 | Tool-calling 不稳定，Agent 会"凭记忆编造"而不是真去查行情 |

</details>

---

## 🏛️ 架构

经典 DDD 4 层（`domain` / `application` / `infrastructure` / `api`）+ 独立 `agents/` 模块（唯一允许 import Agno 的地方）。五条异步 loop 撑起整个系统：一条交易 cycle（AgentOS 调度）+ 四条 10 秒监控器（仓位保护）。

完整 mermaid 图 + 调度拓扑 + 三位一体状态不变量：**[docs/ARCHITECTURE_ZH.md](./docs/ARCHITECTURE_ZH.md)**（[English](./docs/ARCHITECTURE.md)）。

<details>
<summary><b>展开看分层 + 调度图</b></summary>

```mermaid
flowchart TD
    api[api<br/>FastAPI + 中间件 + DI]
    app[application<br/>services、monitors、orchestrators]
    dom[(domain<br/>entities、protocols、纯服务)]
    infra[infrastructure<br/>SQLAlchemy、ccxt、Agno DeepSeek、sqlite-vec]
    agents[agents<br/>Agno Agent + MultiMCPTools + Team]

    api --> app
    app --> dom
    app --> agents
    infra --> dom
    agents --> dom

    classDef dom fill:#fef3c7,stroke:#f59e0b
    class dom dom
```

五条异步 loop，共享同一个注入的 `Clock` 协议：

```mermaid
flowchart LR
    L1[trading_loop<br/>AgentOS scheduler */TRADING_INTERVAL] --> DB[(Postgres + pgvector)]
    L2[account_recorder<br/>cron */ACCOUNT_INTERVAL] --> DB
    L3[trailing_stop<br/>10 秒] --> DB
    L4[stop_loss<br/>10 秒] --> DB
    L5[partial_profit<br/>10 秒原子三位一体 UPDATE] --> DB
    style L5 stroke:#dc2626,stroke-width:3px
```

</details>

---

## 🌐 API 端点

交互式 Swagger 文档：`http://localhost:8000/docs`（渲染实时 spec）。除了 `POST /api/v1/cycle/trigger`、`POST /api/v1/runs/{id}/{confirm,reject}`（T9 HITL）、`POST /api/actions/close-all`（密码保护），其他公开路由全部只读。

<details>
<summary><b>展开看完整端点表</b></summary>

```bash
uv run uvicorn omnitrade.api.app:create_app --factory
# 或：docker compose exec backend ...
```

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` · `/api/ready` | liveness / readiness 探针 |
| `GET` | `/api/account` | 账户余额 + 24h 返佣追踪 |
| `GET` | `/api/positions` | 当前持仓（含三位一体状态） |
| `GET` | `/api/trades` | 成交历史 |
| `GET` | `/api/decisions` | Agent 决策审计日志 |
| `GET` | `/api/history` | 账户净值时间序列 |
| `GET` | `/api/stats` | Sharpe、回撤、策略拆分 |
| `GET` | `/api/prices` | 缓存 ticker |
| `GET` | `/api/strategy` · `/api/config` | 当前策略 + 运行时参数 |
| `GET` | `/api/rebate` | 24h 返佣汇总 |
| `GET` | `/api/logs` | 内存日志缓冲（可 tail） |
| `POST` | `/api/actions/close-all` | 紧急全平仓（有保护） |
| `POST` | `/api/v1/cycle/trigger` | 同步触发一次交易 cycle |
| `POST` | `/api/v1/runs/{run_id}/confirm` · `/reject` | T9 HITL：批准 / 拒绝被暂停的大单 |
| `GET` | `/sse/stream` | Server-Sent Events 流（`decision_update` / `position_update` / `run_paused` / `orchestrator_error` 等） |
| `GET` | `/traces` | AgentOS 暴露的每周期 OTel span 树（T4） |

上述路由同时挂载在 `/api/v1/*` 前缀下；不带前缀的 `/api/*` 是 Phase-8 留下的兼容路径，供仪表盘已有的 fetch 地址继续使用。

</details>

---

## 🗂️ 项目结构

monorepo 两个 app：`apps/backend/`（Python 3.11 / FastAPI / Agno）和 `apps/frontend/`（Next.js 14）。共享基础设施在 `docker-compose.yml`。策略 + 架构深度文档在 `docs/`。

<details>
<summary><b>展开看完整目录树</b></summary>

```
omnitrade/
├── apps/
│   ├── backend/                      # Python 3.11 + FastAPI + SQLAlchemy 2.0
│   │   ├── src/omnitrade/
│   │   │   ├── domain/               # entities、protocols、纯服务
│   │   │   ├── application/          # services、5 条 monitor、multi-agent
│   │   │   ├── infrastructure/       # SQLAlchemy、ccxt、Agno DeepSeek、SSE
│   │   │   ├── agents/               # Agno Agent + MultiMCPTools、prompts
│   │   │   └── api/                  # FastAPI router + 中间件
│   │   ├── alembic/                  # 迁移
│   │   └── tests/                    # 702 绿
│   └── frontend/                     # Next.js 14 + SWR + Server-Sent Events
├── tests/fixtures/frozen/            # 22 份手工策展决策契约
├── docs/                             # 架构 / 策略 / 发布 / ADR
├── assets/                           # logo + social preview + sponsor QR
├── scripts/                          # 运维 + 行为等价 CLI
└── docker-compose.yml                # postgres + pgvector + db-init + backend + frontend
```

</details>

---

## 🛤️ 路线图

| 阶段 | 范围 | 状态 |
|---|---|---|
| 0-7 | DDD 分层、监控器、仪表盘、可观测性 | ✅ 已发 |
| 8.x | 端口桩、多周期数据、LLM 工具、multi-agent 编排、WebSocket 行情流 | ✅ 已发（Agno 切换后 WS 已被 SSE 替换） |
| 9.x | 零共享品牌重构（策略名 / 列名 / fixture ID / cassette 哨兵） | ✅ 已发 |
| 10.x | 依赖许可审计、历史清理 | ✅ 已发 |
| 11 | Postgres + Decimal/Numeric 精度、可观测事件、子智能体 cassette | 📋 规划中 |

---

## 🤝 参与贡献

欢迎 Issue 与 PR。请遵循：

1. 在 `apps/backend` 内跑 `uv run pytest`——**702 个测试必须保持全绿**，22 份固化 fixture 重放通过率 ≥ 0.95。
2. 守 **Agno-only 约束**——`rg "from langgraph|from langchain|import litellm|import mcp2py" apps/backend/src/` 必须为 0。Agno 是这个 codebase 唯一允许的 LLM/Agent/MCP 框架。
3. 守 **三位一体原子性**——任何写入 `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` 的路径都必须走 `PositionRepository.apply_three_way_state`。
4. 新增依赖须在白名单内（MIT / Apache-2.0 / BSD / ISC / MPL-2.0）。参见 [docs/LICENSE_INVENTORY.md](./docs/LICENSE_INVENTORY.md)。

---

## 💖 赞助 — 支持本项目

OmniTrade 是个人 / 志愿者维护的开源项目。如果它帮你在 testnet 上省了
时间、或者将来在 mainnet 上赚到钱，欢迎随手打赏一点 —— 主要会用来
支付 LLM API 调用费、服务器时间、以及偶尔的咖啡因补给。

**USDT（Tron · TRC20）**

```
TMDnFG8KBxNvkgNgqkr9PhL2keNczjSGdS
```

<a href="assets/sponsor-usdt-trc20.svg">
  <img src="assets/sponsor-usdt-trc20.svg" alt="USDT TRC20 收款二维码" width="200" />
</a>

> **⚠️ 网络警告**：这是 **TRON (TRC20)** 地址。如果用 Ethereum / ERC20、
> BSC / BEP20、Polygon、Arbitrum、Solana 等其他链发送 USDT（或任何资产），
> **资金将永久丢失，不可找回**。发送前请确认钱包当前网络是 *Tron*；
> 地址必须复制粘贴整段，错一个字符就是另一个钱包。

没有承诺、没有义务、没有打赏名单、不开发票 —— 只是给想说谢谢的人留一个口子。
如果你更想走 GitHub Sponsors / Open Collective 走正规化通道，
[来开个 issue](https://github.com/gong1414/omnitrade/issues) 推一下。

---

## 🌟 Star 增长 & 贡献者

[![Star History Chart](https://api.star-history.com/svg?repos=gong1414/omnitrade&type=Date)](https://www.star-history.com/#gong1414/omnitrade&Date)

<a href="https://github.com/gong1414/omnitrade/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=gong1414/omnitrade" alt="Contributors" />
</a>

---

## 📄 许可证

MIT，详见 [LICENSE](./LICENSE)。

---

## ⚠️ 免责声明

默认 testnet，也只推荐 testnet。实盘交易承担真实的**全额亏损风险**。维护者**不是金融顾问**，本仓库任何内容都不构成金融建议。自担风险。

---

## 🙏 致谢 — 站在这些开源项目的肩膀上

OmniTrade 站在 ~30 个开源项目肩膀上 —— 从 agent 运行时（Agno + FastMCP + OpenInference）到后端（FastAPI + SQLAlchemy + Postgres + pgvector + ccxt）到前端（Next.js + React + Tailwind + Recharts）到工具链（uv + Ruff + pytest + Playwright）。请大家也给它们点 Star 支持一下。

<details>
<summary><b>展开看完整致谢列表</b></summary>

**Agent 运行时**
- [**Agno**](https://github.com/agno-agi/agno) —— Agent / Team / Workflow / AgentOS 全栈，每一个 cycle 都跑在它上面。Agno 切换之后是项目唯一的 LLM/Agent/MCP 框架。
- [**FastMCP**](https://github.com/jlowin/fastmcp) —— MCP 服务端框架，9 个交易工具 + 6 个加密数据工具的承载层。
- [**OpenInference**](https://github.com/Arize-ai/openinference) —— `AgnoInstrumentor`，把 Agno 的 run / model / tool call 转成 OpenTelemetry span。
- [**OpenTelemetry**](https://github.com/open-telemetry) —— `GET /traces` 背后的 tracing API + SDK。

**大模型 + 向量化**
- [**DeepSeek**](https://www.deepseek.com/) —— 默认对话模型（`deepseek-v4-pro` / `-flash` / `-reasoner`），快、便宜、tool-calling 稳。
- [**fastembed**](https://github.com/qdrant/fastembed) + [**BAAI/bge-small-en-v1.5**](https://huggingface.co/BAAI/bge-small-en-v1.5) —— trade-journal RAG 的本地 384 维 embedder。
- [**hf-mirror.com**](https://hf-mirror.com/) —— 社区维护的 HuggingFace 镜像，让 fastembed 在 cn 网络里也能下到模型。

**后端**
- [**FastAPI**](https://github.com/fastapi/fastapi) + [**Uvicorn**](https://github.com/encode/uvicorn) —— HTTP / SSE 端口。
- [**SQLAlchemy**](https://github.com/sqlalchemy/sqlalchemy) + [**Alembic**](https://github.com/sqlalchemy/alembic) —— 异步 ORM + 迁移工具。
- [**Postgres**](https://www.postgresql.org/) + [**pgvector**](https://github.com/pgvector/pgvector) —— 主存储 + Knowledge 层用的向量索引。
- [**psycopg**](https://github.com/psycopg/psycopg)（3.x） —— 同步 + 异步合一的 PG 驱动，由 SQLAlchemy 路由。
- [**APScheduler**](https://github.com/agronholm/apscheduler) —— 6 个仓位保护监控器的 10 秒定时器。
- [**ccxt**](https://github.com/ccxt/ccxt) —— Gate.io / OKX 统一封装。
- [**structlog**](https://github.com/hynek/structlog) —— 结构化 JSON 日志 + 自动脱敏 processor。
- [**pydantic**](https://github.com/pydantic/pydantic) + [**pydantic-settings**](https://github.com/pydantic/pydantic-settings) —— 配置 + `domain/` 里全部 schema。

**前端**
- [**Next.js 14**](https://github.com/vercel/next.js) —— App Router 仪表盘。
- [**React**](https://github.com/facebook/react) —— UI 运行时。
- [**Tailwind CSS**](https://github.com/tailwindlabs/tailwindcss) —— 样式体系。
- [**Recharts**](https://github.com/recharts/recharts) —— 净值曲线 / confidence-gauge 等图表。
- [**SWR**](https://github.com/vercel/swr) —— 非流式接口的数据拉取。

**工具链**
- [**uv**](https://github.com/astral-sh/uv) —— Python 包管理（比 pip 快 10–100×）。
- [**Ruff**](https://github.com/astral-sh/ruff) —— Lint + format。
- [**pytest**](https://github.com/pytest-dev/pytest) + [**vcrpy**](https://github.com/kevin1024/vcrpy) —— 测试运行器 + cassette HTTP 录回放。
- [**vitest**](https://github.com/vitest-dev/vitest) + [**Playwright**](https://github.com/microsoft/playwright) —— 前端单测 + E2E。
- [**Docker**](https://www.docker.com/) / [**OrbStack**](https://orbstack.dev/) —— 本地栈运行时。

**加密数据源** —— 只读，免费 / freemium：
[CoinGecko](https://www.coingecko.com/)、[Alternative.me 恐惧贪婪指数](https://alternative.me/crypto/fear-and-greed-index/)、[Whale Alert](https://whale-alert.io/)、[Coinglass](https://www.coinglass.com/)、[LunarCrush](https://lunarcrush.com/)、[Etherscan](https://etherscan.io/)、[Gate MCP News](https://api.gatemcp.ai/mcp/news)。

</details>

如果我们漏掉了你的项目，请 [开个 issue][issues] 告诉我们，会立刻补上。
