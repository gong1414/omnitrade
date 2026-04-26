# 参与贡献 OmniTrade

> [English](CONTRIBUTING.md) · 简体中文

谢谢愿意贡献这个项目。这是一个 LLM 驱动的合约期货项目 —— 写错代码可
能在 mainnet 上让用户实际亏钱，所以测试 / 可观测 / 可复现这三条门槛
我们守得很紧。提 PR 之前请通读这篇文档。

> 🛠 想要更深入的开发流程（多种本地开发路径、profiling、调试 recipe、
> 发布流程），见 [DEVELOPMENT_ZH.md](DEVELOPMENT_ZH.md)。这个文档是
> 「契约」，那个文档是「内循环」。

## TL;DR

```bash
# Backend
cd apps/backend
uv sync --all-extras
uv run pytest -m "not manual_qa"          # 必须全绿
uv run ruff check .                        # 必须 clean

# Frontend
cd apps/frontend
npm ci
npm run lint                               # 必须 clean
npm run test                               # vitest

# 全栈（Postgres + pgvector + AgentOS scheduler）
cp .env.example .env                       # 填 secret —— git-ignored
docker compose up -d
curl -X POST http://localhost:8000/api/v1/cycle/trigger
```

## 硬规则（每条都靠真实事故换来的）

这些规则在 `CLAUDE.md` 里给 AI 协作者用，对人类同样适用。

1. **拒绝旧框架**。这个项目只跑 Agno：

   ```bash
   rg "from langgraph|from langchain|import litellm|import mcp2py" apps/backend/src/
   ```

   必须返回 0 命中。任何重新引入这些框架的 PR 一律 reject。

2. **走完用户可见的 G1–G6 验收门**（见 `CLAUDE.md`）再说「完成」。
   `pytest PASS` 是必要不充分条件 —— 我们交付过技术绿但用户用不了的
   改动，付出了代价。

3. **三位一体状态原子性**。任何写入
   `cumulative_close_pct` / `stop_loss` / `trailing_peak_pnl_pct` 的
   代码路径必须走 `PositionRepository.apply_three_way_state`。

4. **22 / 22 固化 fixture 重放**。`apps/backend/tests/behavioral_equivalence/`
   下面的行为等价 cassette 必须能干净重放。如果你有意改 agent 行为，
   重录 cassette 并在 PR 描述里说明 diff。

5. **文档漂移视同 bug**。任何对行为 / 公开 API / 配置 / 架构的改动
   必须更新对应文档：`README.md` + `README_ZH.md`、`CLAUDE.md`
   Project Context、内联 docstring、`docs/ARCHITECTURE.md` + ZH，以及
   `docs/AGNO_MIGRATION_TRACKER.md`（如果触及迁移账本）。

6. **集成测试不许 mock DB**。这是真实事故教的：mock 测试全过，生产
   迁移挂了。打真 DB（sqlite 或 postgres）。

## 项目布局

完整工作目录树见 `CLAUDE.md`。快速定位：

```
apps/
  backend/   FastAPI + Agno Agent + AgentOS + APScheduler (Python 3.11)
  frontend/  Next.js 14 App Router + Tailwind + Recharts (SSE 单一推流)
docs/
  ARCHITECTURE.md        DDD 分层、scheduler 拓扑、三位一体状态
  AGNO_MIGRATION_TRACKER.md   T1–T10 + Acceptance 1–4 账本
.github/
  workflows/ci.yml       backend pytest、frontend lint、ReliabilityEval
.omc/                    spec / plan / autopilot artifact（仅 planning）
```

## 开发环境

### 必备
- Python 3.11
- Node.js 20+
- Docker + Docker Compose（Postgres + pgvector + AgentOS 路径）
- `uv`（`pipx install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh | sh`）

### 推荐
- DeepSeek API key（chat），填到 `LLM_API_KEY`
- 一个 Gate.io **testnet** 账户（mainnet 默认关闭 ——
  `GATE_USE_TESTNET=true` 在 `.env.example` 里）

### 第一次启动
```bash
git clone https://github.com/<your-fork>/omnitrade.git
cd omnitrade
cp .env.example .env                # 至少填 LLM_API_KEY
docker compose up -d                # postgres + db-init + backend + frontend
docker compose logs backend --tail 100
open http://localhost:3000/dashboard
```

## 测试

| 范围 | 路径 | 命令 |
|---|---|---|
| Backend 单测 + 集成 | `apps/backend/tests/` | `cd apps/backend && uv run pytest -m "not manual_qa"` |
| Backend evals（Reliability + Accuracy） | `tests/eval/` | `uv run pytest -m eval` |
| Backend manual_qa（live LLM） | various | `uv run pytest -m manual_qa`（需要 `LLM_API_KEY`） |
| Frontend lint | `apps/frontend/` | `npm run lint` |
| Frontend 单测（vitest） | `apps/frontend/components/__tests__/` | `npm run test` |
| Frontend E2E（Playwright） | `apps/frontend/tests/e2e/` | `npm run test:e2e` |
| Acceptance 3 — 11 策略 | `tests/agents/test_strategies_acceptance3.py` | 包含在默认 lane |
| Spec acceptance 4（旧 import） | 全仓 | `rg "from langgraph\|from langchain\|import litellm\|import mcp2py" apps/backend/src/` 应为 0 |

backend 默认 lane <30 秒。全套 + frontend lint 在现代笔记本上 < 1 分钟。

## Commit & PR 风格

约定式提交（Conventional Commits）+ scope：

```
feat(backend):  backend 新功能
fix(frontend):  frontend bug 修复
docs:           仅文档
test(backend):  仅测试
chore(infra):   工具链 / CI / build
refactor:       行为不变
```

- 第一行 ≤ 70 字符
- body 解释 **为什么**（diff 已经显示了「什么」）
- AI 协作的 commit 在 footer 加 `Co-Authored-By:`

分支策略：

- 从 `main` 拉 feature 分支
- 提 PR 前 rebase（不要 merge commit）
- 默认 squash merge（小修补）；大 feature 保留历史

## PR checklist

请人 review 之前确认：

- [ ] `apps/backend/` 里 `uv run pytest -m "not manual_qa"` 全绿
- [ ] `apps/frontend/` 里 `npm run lint` clean
- [ ] 改动到用户可见的部分，已经在本地走过 `CLAUDE.md` 的 G1–G6，截
      图或 curl 输出可以贴出来
- [ ] 加了公开 API / schema / env var，已经更新 `.env.example`（根 +
      `apps/backend/`）、对应 README、`CLAUDE.md` Project Context
- [ ] 没有引入许可白名单外的依赖（MIT / Apache-2.0 / BSD / ISC /
      MPL-2.0）。不确定就在 PR 里列出来
- [ ] tracked 文件没有 secret（`git diff --cached | rg "sk-[A-Za-z0-9]{20,}"`）

## 报 bug / 提需求

请走 `.github/ISSUE_TEMPLATE/` 下的 issue 模板。**安全问题走
[SECURITY_ZH.md](SECURITY_ZH.md)**，不要开公开 issue。

## 行为准则

本项目遵循 [Contributor Covenant 2.1](CODE_OF_CONDUCT_ZH.md)。参与
即表示你同意遵守。
