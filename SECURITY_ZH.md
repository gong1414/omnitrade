# 安全策略

> [English](SECURITY.md) · 简体中文

OmniTrade 在加密货币交易所自动执行真实交易。这里的安全问题会直接造
成资金损失，所以我们认真对待、快速响应。

## 上报漏洞

**请不要在 GitHub 公开开 issue 报告安全问题。**

请通过 GitHub 仓库主页上的邮箱私下联系维护者，或者使用 GitHub 自带
的 [Private Vulnerability Reporting][pvr] 功能。

[pvr]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability

请附上：

- 漏洞描述与影响范围
- 复现步骤（一个最小可复现 case 最理想）
- 受影响的 commit / version
- 你已经识别到的缓解措施（如果有）

我们的目标：

- **72 小时内**确认收到
- **7 天内**给出初步评估
- 关键问题**30 天内**发布修复或缓解措施

如果你愿意（且同意），我们会在安全公告里 credit 你。

## 范围

**在范围内**：

- Backend（`apps/backend/`）
- Frontend（`apps/frontend/`）
- Docker compose / 部署面（`docker-compose*.yml`、`apps/*/Dockerfile`）
- 默认配置（`.env.example` 文件）
- LLM agent / tool 路由（任何可能导致非预期交易的代码）
- 认证 / 授权路径（HITL approve/reject 端点、AgentOS overlay）
- secret 处理与凭证泄漏

**不在范围**：

- 上游依赖的漏洞（请向上游项目报告；我们会在 patch 出来后吸收）
- 用你自己 API key 通过 LLM token 用量造成的 DoS
- 需要物理接触操作员机器的问题

## 威胁模型 — 我们明确防御什么

- **幻觉持仓** —— AI 把交易所上不存在的持仓当成真的。由 G6 跨源一
  致性检查（决策 JSON vs `/api/v1/positions` vs `/api/v1/account`）
  缓解。任何不一致都是 bug。
- **意外大单** —— T9 HITL 暂停超过
  `HITL_OPEN_SIZE_THRESHOLD_USD`（默认 1 万美元）的开仓，等操作员通
  过仪表盘 banner 批准。这个 pause loop 包在 `record_open_decision`
  工具自身上，不是包在 API 表面 —— 任何新加的 open 路径都自动继承
  这道门。
- **日内亏损失控** —— `DailyLossLimiter` 在今日实现 PnL 跌破
  `-DAILY_LOSS_CAP_USDT` 后，把 open / close / partial_close 强制
  改写为 `hold`。
- **意外切到 mainnet** —— `GATE_USE_TESTNET=true` 和
  `OKX_USE_TESTNET=true` 都是默认。tracker 文档和 `.env.example`
  反复提示这一点。
- **secret 泄漏** —— `.env`、`.env.local`、`*.production` 都在
  `.gitignore` 里。CI 不 echo env 值。日志通过 `structlog` processor
  剥除 secret 字段。
- **LLM 数据外泄** —— agent 只能访问 `coingecko` / `fear & greed` /
  `whale alert` / `coinglass` / `etherscan` / `lunar crush` 这类只
  读数据源，再加上 4 个决策工具和 9 个交易工具。它**够不到任意 HTTP**
  端点。给 agent 加新 MCP server 时会按这个契约 review。

## 操作员的责任

即使我们做了上面的加固，**你**仍然要负责：

- **绝不 commit `.env` 或任何含真实凭证的文件**。`.gitignore` 挡了
  常见路径，但 secret 滑进测试 fixture 或 commit 信息还是你的问题。
- **从 testnet 起步**。`GATE_USE_TESTNET=true` 是默认；切到 `false`
  是个有意识的决策。在 mainnet 试运行之前先 testnet 跑数周，初始余
  额「亏得起但又有意义」。
- **疑似泄露立刻轮换 key**。怀疑 leak 就立刻轮换被影响的交易所 API
  key。Gate / OKX 上每个 key 默认设成「仅交易、禁止提现」—— 提现
  应该锁在交易所侧的 2FA 后面。
- **每个 cycle 的推理都读**。LLM 的 `market_context` /
  `gates_passed` / `justification` 是免费的 QA 通道。G5 故障短语
  post_hook（T3）自动捕捉 11 种已知失败短语，但用心的人还是最后一
  道防线。
- **把 `HITL_OPEN_SIZE_THRESHOLD_USD` 设成你的容忍线**。默认 1 万对
  小型 testnet 账户偏保守，对一些用户可能偏高。改成你愿意手动批准
  的名义价值。

## 自动化安全工具

仓库开启了所有 GitHub 对公共项目免费的安全功能：

- **CodeQL 代码扫描**（`.github/workflows/codeql.yml`）— 每次 push、
  PR、每周定时跑 `security-and-quality` 规则集，覆盖 Python +
  JS/TS。结果在 [Security → Code scanning][cs] 下看。
- **Copilot Autofix** — CodeQL 找到新告警后，GitHub 自动给出补丁建
  议，从告警页直接 commit 即可。公共仓免费，无需配置。
- **Dependabot 漏洞告警** — 我们用的依赖一进 GHSA 数据库，Security
  tab 立刻提示。
- **Dependabot 安全更新** — 自动开 PR 把补丁版本钉死。主版本升级被
  策略屏蔽（`.github/dependabot.yml`）；patch + minor 合并成组。
- **Secret scanning + push 拦截** — pre-receive hook 拒绝任何含已知
  格式 token（AWS / Slack / GitHub PAT / Stripe …）的 push，绕过会
  留日志。
- **PR 自动格式化**（`.github/workflows/autoformat.yml`）— 同仓库 PR
  会跑 `ruff format` + `ruff check --fix-only`，把结果作为
  `style: auto-format` commit 推回去，让人工 review 只看逻辑，不看
  空格。

[cs]: https://github.com/gong1414/omnitrade/security/code-scanning

## 披露历史

每次安全问题被修复，这里会更新。

— *最近一次审阅 2026-04-26.*
