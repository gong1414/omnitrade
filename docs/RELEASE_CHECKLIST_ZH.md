<p align="right">
  <a href="./RELEASE_CHECKLIST.md">English</a> | <b>简体中文</b>
</p>

# OmniTrade —— 发布清单（可 dry-run）

> 线性清单，用于切生产发布。每条都带 shell 片段，可直接执行或粘到自己的 runbook。
> **本清单是建议性的** —— 打 tag 和任何外部发布操作由维护者（你）手工执行。CI 只做校验，不打 tag、不发布。

默认环境：仓库根目录（`/path/to/llmtrading`）、PATH 里有 `uv` 和 `npm`、Docker 守护进程运行中。

---

## 1 · 预检 —— 仓库健康

- [ ] **所有历史阶段 HANDOFF 都在 `docs/history/`：**

  ```bash
  ls docs/history/HANDOFF-phase-*.md
  ```

  预期：至少 9 份（phase-0..7 + 4.5）。

- [ ] **工作树干净：**

  ```bash
  git status --short
  # 预期：空
  ```

- [ ] **commit 历史覆盖所有阶段：**

  ```bash
  git log --oneline --grep='phase-' | head -30
  ```

---

## 2 · 后端门

- [ ] **Ruff lint + format：**

  ```bash
  cd apps/backend
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  ```

- [ ] **mypy strict：**

  ```bash
  uv run mypy --strict src/
  ```

- [ ] **pytest 覆盖率 ≥ 80 %：**

  ```bash
  uv run pytest tests/ -q --cov=src/omnitrade --cov-fail-under=80
  ```

- [ ] **结构化输出契约门：**

  ```bash
  uv run pytest tests/agents/test_structured_output_contract.py tests/agents/test_tool_aware_gate.py -q
  ```

---

## 3 · 前端门

- [ ] **类型检查：**

  ```bash
  npm run type-check --workspace apps/frontend
  ```

- [ ] **Lint：**

  ```bash
  npm run lint --workspace apps/frontend
  ```

- [ ] **生产构建：**

  ```bash
  npm run build --workspace apps/frontend
  ```

- [ ] **Playwright e2e（Chromium）：**

  ```bash
  cd apps/frontend
  npx playwright install --with-deps chromium
  npx playwright test --project=chromium
  cd ../..
  ```

---

## 4 · Docker 合法性

- [ ] **dev compose 可解析：**

  ```bash
  docker compose config >/dev/null && echo "dev: OK"
  ```

- [ ] **prod compose 可解析：**

  ```bash
  docker compose -f docker-compose.prod.yml config >/dev/null && echo "prod: OK"
  ```

- [ ] **镜像可构建：**

  ```bash
  docker compose -f docker-compose.prod.yml build --pull
  ```

---

## 5 · 品牌扫描

- [ ] **已发布源码里零品牌泄漏：**

  ```bash
  ! rg -n 'NOFIAIOO|195440|nof1\.ai|voltagent' \
      --glob '!docs/history/**' \
      --glob '!node_modules/**' \
      --glob '!.omc/**' \
      --glob '!.venv/**' \
      apps/ docs/ README*.md \
    && echo "brand scrub: CLEAN"
  ```

  预期：0 命中。

---

## 6 · Secret / 环境变量

- [ ] **`.env.production` 在主机上存在但 NOT in git：**

  ```bash
  test -f .env.production || echo "MISSING .env.production —— 从 .env.production.example 复制"
  git ls-files .env.production
  # 预期：空
  ```

- [ ] **必要 secret 已填（非空）：**

  ```bash
  grep -E '^(LLM_API_KEY|GATE_API_KEY|GATE_API_SECRET)=' .env.production | grep -v '=$'
  ```

- [ ] **Testnet 标志和意图一致：**

  ```bash
  grep -E '^(GATE_USE_TESTNET|OKX_USE_TESTNET|ENVIRONMENT)=' .env.production
  # dry-run 时设 true / testnet
  ```

---

## 7 · 数据安全

- [ ] **备份当前生产 DB：**

  ```bash
  ts=$(date +%Y%m%dT%H%M%S)
  cp data/omnitrade.db "data/omnitrade-${ts}.db.bak"
  ls -lh data/omnitrade-*.db.bak | tail -3
  ```

- [ ] **在副本上 dry-run 迁移：**

  ```bash
  cp "data/omnitrade-${ts}.db.bak" /tmp/omnitrade-dryrun.db
  DATABASE_URL=sqlite:////tmp/omnitrade-dryrun.db \
    uv --project apps/backend run alembic upgrade head
  ```

---

## 8 · 部署

- [ ] **停掉现有 stack（如有）：**

  ```bash
  docker compose -f docker-compose.prod.yml down
  ```

- [ ] **应用 schema 迁移：**

  ```bash
  docker compose -f docker-compose.prod.yml run --rm db-init
  ```

- [ ] **启动 stack：**

  ```bash
  docker compose -f docker-compose.prod.yml up -d
  ```

---

## 9 · 部署后冒烟

- [ ] **健康轮询（5 分钟或 healthy 前）：**

  ```bash
  for i in $(seq 1 30); do
    status=$(docker inspect --format '{{.State.Health.Status}}' omnitrade-backend 2>/dev/null)
    echo "tick $i: backend=$status"
    [ "$status" = "healthy" ] && break
    sleep 10
  done
  ```

- [ ] **curl /health：**

  ```bash
  curl -fsS http://localhost:8000/health
  ```

- [ ] **仪表盘返回 index：**

  ```bash
  curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/
  # 预期：200
  ```

- [ ] **可观测性冒烟 —— 日志里有 correlation id：**

  ```bash
  req_id=$(uuidgen)
  curl -fsS -H "X-Request-ID: $req_id" http://localhost:8000/api/account >/dev/null
  docker compose -f docker-compose.prod.yml logs --tail=200 backend | grep -c "$req_id"
  # 预期：≥ 1
  ```

- [ ] **至少一条 trading loop 已跑完：**

  ```bash
  docker compose -f docker-compose.prod.yml logs --since=10m backend | \
    grep -E 'trading_loop.*(started|completed)'
  ```

---

## 10 · 打 tag（维护者手工执行）

> Agent 执行器**禁止**跑这一步。Tag 签名是维护者的动作。

- [ ] **创建签名 tag：**

  ```bash
  git tag -s v1.0.0 -m "v1.0.0 — OmniTrade Python DDD"
  ```

- [ ] **推送 tag：**

  ```bash
  git push origin v1.0.0
  ```

---

## 11 · 回滚计划

如果 health 失败或冒烟有问题：

- [ ] **停掉新 stack + 从备份恢复 DB：**

  ```bash
  docker compose -f docker-compose.prod.yml down
  cp "data/omnitrade-${ts}.db.bak" data/omnitrade.db
  ```

- [ ] **切回上一个 tag + 重新部署：**

  ```bash
  prev_tag=$(git describe --tags --abbrev=0 HEAD^)
  git checkout "$prev_tag"
  docker compose -f docker-compose.prod.yml up -d
  ```

- [ ] **验证老版本健康：**

  ```bash
  curl -fsS http://localhost:8000/health
  ```

---

## 12 · 已知 follow-up

以下是已被识别的延期项，**都不阻塞** v1.0.0 发布：

- **F-UP 1：** ~~VCR cassette 刷新 runbook~~ —— 已在 PR-B2 Phase D 退役；历史背景见 [VCRPY_REFRESH_ZH.md](./VCRPY_REFRESH_ZH.md)。
- **F-UP 2：** Postgres 兼容的 repository（SQLite 是默认发布目标）。
- **F-UP 3：** Mainnet 审计 + 红队演练 —— 切换 `*_USE_TESTNET=false` 前必须完成。
- **F-UP 4：** 默认 compose 里加 Redis（目前在 `--profile cache` 后）。
