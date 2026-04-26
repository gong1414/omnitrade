# FAQ — 常见问答与错误兜底

> [English](FAQ.md) · 简体中文

如果你遇到的问题这里没有，欢迎 [开 issue][issues] —— 我们会补上。

[issues]: https://github.com/gong1414/omnitrade/issues

## 配置

### Q：我只有 OpenAI / OpenRouter 的 key，能用吗？

可以。OmniTrade 跑在 Agno 的 `DeepSeek` model class 上，但底层 HTTP
是 OpenAI 兼容的。配置：

```env
LLM_API_KEY=sk-...                     # OpenAI / OpenRouter key
LLM_BASE_URL=https://api.openai.com/v1 # 或者 OpenRouter / 聚合服务的 base
AGNO_LLM_MODEL=gpt-5.4                 # 或该服务支持的模型名
```

embedder 也一并切到 OpenAI 协议：

```env
EMBEDDER_PROVIDER=openai
EMBEDDER_API_KEY=sk-...                # 通常和 LLM 用同一个 key
EMBEDDER_BASE_URL=https://api.openai.com/v1
```

### Q：第一次启动卡在「Downloading BAAI/bge-small-en-v1.5」

embedder 模型第一次跑会从 `huggingface.co` 下载。如果你在国内网络，
默认 TLS 握手会超时。我们已经在 `docker-compose.yml` 里通过
`HF_ENDPOINT` 走 `https://hf-mirror.com`，理论上「拿来即用」——但如果
还是卡：

```bash
docker compose logs backend --tail 50
# 找 HFError / SSL / connection timeout
```

如果看到 SSL 错误，说明你的网络也屏蔽了 `hf-mirror.com`。绕路方案：
手动把 `BAAI/bge-small-en-v1.5` 下载到 `./hf_cache/huggingface/hub/`
（这个 volume 已经挂载好了），然后重启。

### Q：能不用 Docker 吗？

可以，看 README → Path B（本地 Python 3.11 + Node 20）。需要 `uv`、
一个能连上的 Postgres + pgvector 实例，并把 `DATABASE_URL` 在 `.env`
里指向它。

## 运行时

### Q：`curl /api/v1/cycle/trigger` 504 / 超过 60 秒

最常见原因，按概率排：

1. **reasoner 模型本来就慢**：`deepseek-reasoner` 跑陪审团策略经常
   100–200 秒。把 `cycle_trigger_timeout_seconds`（默认 60）调到
   180+，或者 `AGNO_LLM_MODEL` 切回 `deepseek-v4-flash`。
2. **被限流了**：backend 日志里找 LLM 提供商的 HTTP 429。DeepSeek
   免费额度宽松但不是无限。
3. **某个 MCP server 卡住了**：15 个 MCP 工具（9 交易 + 6 加密数据）
   里某一个超时。10 秒监控器循环不会被影响，但主 think function
   会等。`docker compose logs backend | grep -i mcp` 看一下。

### Q：AI 的 `market_context` 出现「数据同步故障」之类的话

这是 **G5 故障短语 post_hook** 触发了。当 bug ticket 处理：AI 在告
诉你「我观察到的东西和现实不一致」。最常见是仓位同步 worker 还没追
上、或者交易所返回了畸形数据。检查：

```bash
curl -s http://localhost:8000/api/v1/positions | jq
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq '.positions_count'
# 这两个数必须一致。不一致 = G6 跨源 bug。
```

### Q：超过 1 万美元的开仓没触发，挂在那里

这是 **T9 HITL gate** 在干活。美元名义价值超过
`HITL_OPEN_SIZE_THRESHOLD_USD`（默认 1 万）的开仓会暂停等操作员批
准。看 `http://localhost:3000/dashboard` 上的批准 banner，点 Approve
或 Reject。或者通过 API：

```bash
curl -X POST http://localhost:8000/api/v1/runs/{run_id}/confirm
```

调高阈值：

```env
HITL_OPEN_SIZE_THRESHOLD_USD=50000
```

完全关闭（mainnet 不建议）：

```env
HITL_OPEN_SIZE_THRESHOLD_USD=99999999     # 实质上禁用
```

### Q：`daily_loss_cap` 触发了，所有决策都改写成 `hold`

**DailyLossLimiter** 在工作：今天的实现 PnL 跌破
`-DAILY_LOSS_CAP_USDT` 时，下一轮的 open / close / partial_close 会
被强制改写为 `hold`。UTC 午夜重置。调高上限：

```env
DAILY_LOSS_CAP_USDT=500.0
```

### Q：怎么不重启就切策略？

目前必须重启 backend —— `TRADING_STRATEGY` 是启动时加载一次。热切换
端点在 roadmap 上，如果你觉得有用就 +1 那个 issue 或者直接 PR 一个
草案。

## 开发

### Q：pytest 报 `psycopg.OperationalError`

backend 测试套默认用 SQLite（`aiosqlite`）。如果你看到 psycopg 错误，
说明 `DATABASE_URL` 指向 Postgres 但 Postgres 服务不在线。要么开
（`docker compose up postgres`），要么覆盖：

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/test.db uv run pytest
```

### Q：我的 PR CI `mypy --strict` 挂了

OmniTrade 锁 `mypy --strict`，因为 agent 工具层对类型敏感（一个错
类型的 kwarg 会让 tool-calling 静默挂掉）。PR 模板里有本地复现命令，
push 前跑一遍。

### Q：怎么加新策略？

最少改动：

1. `domain/enums.py::StrategyName` 加一个新成员
2. `agents/prompts/` 放一个新 prompt 文件
3. 在 `agents/trading_agent.py::build_agno_think_fn` 的策略分发器里
   加一支
4. `tests/agents/test_strategies_acceptance3.py` 加一行 —— 每个策略
   必须确定性地完成一次 cycle（不调 LLM）
5. 更新 `docs/STRATEGIES_ZH.md`

22 份固化 fixture 重放门必须仍然 ≥ 0.95 通过。

## 运维

### Q：怎么在生产环境监控 cycle？

每个 cycle 都会发出一棵 OpenTelemetry span 树（T4）。最简单：

```bash
curl -s http://localhost:8000/traces | jq    # AgentOS trace API
```

每个 span 显示 model 调用、tool 调用、耗时。要长期存储，把现有 OTel
collector 指过来即可（Agno 的 tracing setup 遵循标准 `OTEL_*` env）。

### Q：能扩展到多用户/多账户吗？

当前设计假设「一个部署对应一个操作员」。多租户支持（每用户独立交易
账户、隔离 agent state）**不在 1.0 范围**。如果是你的用例，开个 issue
讨论形状 —— 这是个体量较大的设计决策。
