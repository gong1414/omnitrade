# 开发指南

> [English](DEVELOPMENT.md) · 简体中文

这是 OmniTrade 自身开发的深度指南。建议阅读顺序：

1. [README_ZH.md](README_ZH.md) — 项目是什么、用户角度怎么跑
2. [CONTRIBUTING_ZH.md](CONTRIBUTING_ZH.md) — 契约：硬规则、PR 检查表、commit 风格
3. **DEVELOPMENT_ZH.md**（本文档）— 内循环：每一层怎么跑 / 调 / profile / 扩展
4. [docs/ARCHITECTURE_ZH.md](docs/ARCHITECTURE_ZH.md) — 各层背后的「为什么」

只想跑起来用？看 [docs/QUICKSTART_ZH.md](docs/QUICKSTART_ZH.md)，5 分钟搞定。

## 1. 本地环境

### 路径 A — Docker（最贴近 CI）

```bash
cp apps/backend/.env.example .env
docker compose up -d
docker compose logs backend -f
```

优点：postgres + pgvector + db-init + backend + frontend 全套一起起。
缺点：首次启动 ~3 分钟（镜像 build + 下 `BAAI/bge-small-en-v1.5`），
attach debugger 麻烦。

### 路径 B — 本地 Python + Node（最快内循环）

```bash
# Backend（一个终端）
cd apps/backend
uv sync --all-extras
uv run alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./data/dev.db \
  uv run uvicorn omnitrade.api.app:create_app --factory --reload --port 8000

# Frontend（另一个终端）
cd apps/frontend
npm install
npm run dev   # http://localhost:3000
```

优点：秒级重启、`pdb` 可用、IDE 调试舒服。
缺点：仅 SQLite（无 pgvector）；T10 RAG 层在 SQLite 上是 no-op ——
有意为之，但你看不到 Knowledge 入库。

### 路径 C — 混合（Postgres on Docker + backend on host）

```bash
docker compose up -d postgres                                       # 只起 PG + pgvector
DATABASE_URL=postgresql+psycopg://omnitrade:omnitrade@localhost:5432/omnitrade \
  uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://omnitrade:omnitrade@localhost:5432/omnitrade \
  uv run uvicorn omnitrade.api.app:create_app --factory --reload
```

最适合调 T10 RAG / migration / pgvector 查询，同时保持本地 Python 快
速迭代。

## 2. 内循环

### Backend 测试

```bash
cd apps/backend
uv run pytest -m "not manual_qa"                            # CI-safe（~25 秒）
uv run pytest tests/agents/                                 # 仅 agent 层
uv run pytest -m eval                                       # T7 ReliabilityEval + T8 AccuracyEval
uv run pytest -m manual_qa                                  # live LLM（需 LLM_API_KEY）
uv run pytest tests/agents/test_strategies_acceptance3.py   # 11 策略 × cycle
uv run pytest tests/behavioral_equivalence/                 # 22-fixture 重放
```

覆盖率：

```bash
uv run pytest --cov=src/omnitrade --cov-report=html
open htmlcov/index.html
```

### Backend lint / type-check

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy --strict src/
```

CI 跑这三项；PR 必须过。本地 pre-commit hook 跑同样的 —— 装一下：

```bash
uv tool install pre-commit
pre-commit install
```

### Frontend 测试

```bash
cd apps/frontend
npm run lint
npm run type-check
npm run test                       # vitest
npm run test:e2e                   # Playwright（需要 backend 在跑）
```

### 单 cycle 冒烟

最快「我有没有打断端到端」的检查：触发一次 cycle 然后读决策 JSON：

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq
```

宣布 PR 完成之前也是这样走 [G1–G6 验收门](CLAUDE.md)。

## 3. 数据库

### Migration

```bash
uv run alembic upgrade head                  # 全部应用
uv run alembic downgrade -1                  # 回退一步
uv run alembic history                       # 列出 revision
uv run alembic revision -m "your change"     # 起一个新 revision
```

Revision 在 `apps/backend/alembic/versions/`。最近的几个在
[`apps/backend/README.md`](apps/backend/README.md) 里有说明。

新加 migration **必须**验证 upgrade 和 downgrade 能 round-trip：

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

如果 `downgrade()` 不能写或会破坏数据，在 migration 的 docstring 里
说明原因。

### 看 DB 内容

```bash
docker compose exec postgres psql -U omnitrade -d omnitrade
\dt ai.*
\d agent_decisions
SELECT id, run_id, action, structured_confidence FROM agent_decisions ORDER BY id DESC LIMIT 5;
```

SQLite（路径 B）：

```bash
sqlite3 apps/backend/data/dev.db
.tables
.schema agent_decisions
```

## 4. 加东西

### 加新策略

1. 在 `domain/enums.py::StrategyName` 加成员
2. 在 `agents/prompts/` 放 prompt 文件
3. 在 `agents/trading_agent.py::build_agno_think_fn` 的 selector 接一支
4. 在 `tests/agents/test_strategies_acceptance3.py` 加一行 —— 每个
   策略必须确定性完成一次 cycle（不调 LLM）
5. 更新 `docs/STRATEGIES_ZH.md`
6. 重跑 22 份固化 fixture 门，必须 ≥ 0.95

### 加新 MCP 工具

1. 在 `infrastructure/mcp/` 或 `infrastructure/data_sources/` 下的
   FastMCP server 里加函数
2. `MultiMCPTools` 通过 stdio 自动发现
3. 用 `manual_qa` 标记的测试在 `tests/agents/` 下测
4. 更新 [`docs/TOOL_INVENTORY_ZH.md`](docs/TOOL_INVENTORY_ZH.md)

### 加新仪表盘 panel

1. 在 `apps/frontend/components/` 加 React 组件
2. 通过 `useRealtime` hook 接入（单一 SSE 真相源）
3. 在 `components/__tests__/` 加一个 vitest 快照
4. 更新 `assets/` 里的截图（手动）

### 加新 env var

1. 在 `apps/backend/src/omnitrade/config.py::Settings` 加字段
2. `apps/backend/.env.example` 和根 `.env.example` 都加一行 + 注释
3. 用户可见的话，在 [README.md](README.md) 和
   [README_ZH.md](README_ZH.md) 的环境变量表里加一行
4. PR 模板的 checklist 会在提交时提醒

## 5. 调试 recipe

### 「AI 在幻觉持仓」

```bash
curl -s http://localhost:8000/api/v1/positions | jq
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq '.positions_count'
# 这两个数必须一致。不一致 = G6 跨源 bug。
```

`infrastructure/exchange/ccxt_exchange.py::fetch_positions` 只读
`contracts`，绝不读 `contractSize` —— 这是历史修复点。

### 「cycle 卡住 / 跑得超久」

```bash
docker compose logs backend --tail 200 | grep -i 'mcp\|timeout\|429\|rate'
# 常见原因：
#   - LLM 提供商被限流（HTTP 429）
#   - reasoner 模型本来就慢（调高 cycle_trigger_timeout_seconds）
#   - 某个 MCP server 超时（其他 14 个还能跑）
```

### 「每周期的 trace 在哪？」

```bash
curl -s http://localhost:8000/traces | jq
# AgentOS 服务出去的。每个 entry 是一次 Agno run，下面挂完整 span 树
# （model 调用、tool 调用、hook）。
```

### 「G5 故障短语触发了」

agent 的 `market_context` / `gates_passed` / `justification` 出现了
11 种已知失败短语之一。**别忽略**，去查。完整短语列表见
`agents/guardrails/qa_phrase.py`。

## 6. 性能

默认 cycle（单 agent、`deepseek-v4-flash`、2 个 symbol）墙上时间约
30–60 秒。`arena-tribunal` 配 `deepseek-reasoner` 可能跑 100–200 秒。

需要提速：

- `AGNO_LLM_MODEL` 切 `deepseek-v4-flash`（最便宜 + 最快）
- 关 team advisory（`MULTI_AGENT_ENABLED=false`）
- 把 `TRADING_SYMBOLS` 砍到你真正想看的几对
- 调小 `ACCOUNT_RECORD_INTERVAL_MINUTES`，前提是你不在乎净值曲线粒度

### profile 一次 cycle

```bash
uv run python -c "
import asyncio, cProfile, pstats
from omnitrade.application.composition import build_trading_monitor
async def main():
    mon = await build_trading_monitor(...)  # 看 tests/ 下的 fixture
    cProfile.runctx('asyncio.run(mon.tick())', globals(), locals(), 'cycle.prof')
asyncio.run(main())
"
uv run python -m pstats cycle.prof << 'EOF'
sort cumulative
stats 30
EOF
```

## 7. 发布流程

1. `main` 上 CI 全绿
2. 更新 `CHANGELOG.md` —— 把 `Unreleased` 项移到新版本段
3. 本地打 tag：`git tag v0.x.0 -m "release notes"`
4. push：`git push origin v0.x.0`
5. 建 GitHub release（`gh release create v0.x.0 --notes-from-tag`
   或从 `CHANGELOG.md` 复制过去）
6. 把 README 顶部 `📰 News` 段加一条新更新

## 8. 在哪问

- **Bug** → [bug 模板的 issue](https://github.com/gong1414/omnitrade/issues/new?template=bug_report.md)
- **新需求** → [feature 模板的 issue](https://github.com/gong1414/omnitrade/issues/new?template=feature_request.md)
- **架构 / 设计讨论** → [Discussions](https://github.com/gong1414/omnitrade/discussions)
- **安全** → [SECURITY_ZH.md](SECURITY_ZH.md)（私有渠道 —— 不要开 issue）
