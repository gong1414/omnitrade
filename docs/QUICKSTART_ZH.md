# 快速开始 — 5 分钟跑通第一个 cycle

> [English](QUICKSTART.md) · 简体中文

最短的从 `git clone` 到「Agent 在 Gate.io testnet 上自动交易」的路径。
每一步都是一条命令。如果踩坑，跳到 [docs/FAQ_ZH.md](FAQ_ZH.md)，
常见错误都在那里附上可粘贴的修法。

> ⚠️ **第一次先 testnet**。Mainnet 必须显式 `GATE_USE_TESTNET=false`，
> 在那之前我们建议先在 testnet 上跑数周。详见
> [SECURITY_ZH.md](../SECURITY_ZH.md) 和 README 的风险提示段。

## 前置条件

- Docker + Docker Compose（macOS 推荐 [OrbStack](https://orbstack.dev/)）
- 一个 DeepSeek API key — https://platform.deepseek.com 注册即送（30 秒搞定，无需付费）
- 一个 Gate.io **testnet** 账户 — https://www.gate.io/testnet 直接领免费 testnet USDT

## 1. clone

```bash
git clone https://github.com/gong1414/omnitrade.git
cd omnitrade
```

## 2. 配置

```bash
cp apps/backend/.env.example .env
```

打开 `.env`，**只需要填三个 key** 就能跑起来：

| Key | 在哪拿 |
|---|---|
| `LLM_API_KEY` | https://platform.deepseek.com → API keys |
| `GATE_API_KEY` | Gate.io testnet → Account → API |
| `GATE_API_SECRET` | 同一页 |

其他全部保留默认。`GATE_USE_TESTNET=true` 是默认值，所以是隔离沙箱。

## 3. 启动整套栈

```bash
docker compose up -d
```

这会拉起 Postgres + pgvector，跑一次 Alembic 迁移，然后启动 backend
（FastAPI + AgentOS）和 frontend（Next.js）。首次启动 ~3 分钟（镜像
build + 走中文 HF 镜像下载 `BAAI/bge-small-en-v1.5` embedder 模型）。

确认 backend 活着：

```bash
curl -fsS http://localhost:8000/health
# → {"status":"ok"}
```

## 4. 触发第一次 cycle

```bash
curl -X POST http://localhost:8000/api/v1/cycle/trigger
# → {"status":"ok","elapsed_seconds":42}
```

## 5. 读结果

```bash
curl -s 'http://localhost:8000/api/v1/decisions?limit=1' | jq
```

应该看到一段 `StructuredReason` JSON，其中 `market_context` /
`gates_passed` / `invalidation_condition` / `plan` / `confidence` /
`justification` / `output_language` 全部填满。

## 6. 打开仪表盘

```
http://localhost:3000/dashboard
```

最新一轮 cycle 的推理会以 5-panel 布局渲染（Market Context / Gates /
Invalidation / Plan / ConfidenceGauge）。之后会按
`TRADING_INTERVAL_MINUTES`（默认 20 分钟）自动循环。

---

## 接下来做什么

- **换策略**：把 `.env` 里的 `TRADING_STRATEGY` 改成 `docs/STRATEGIES_ZH.md`
  里列的 11 个策略名其中之一，然后 `docker compose restart backend`
- **收紧安全网**：把 `HITL_OPEN_SIZE_THRESHOLD_USD` 调到你能接受
  「我必须人工批准」的金额（默认 1 万美元）。超过这个金额的开仓会
  通过 SSE 暂停，等你在仪表盘 banner 上批准
- **看 traces**：`http://localhost:8000/traces` 给出每个 cycle 的
  OpenTelemetry span 树（每一次 Agno tool call、model call、hook 都有）
- **每个 cycle 的 justification 都读一遍**：AI 的 `gates_passed` 和
  `justification` 是免费的 QA 通道。G5 故障短语扫描器会自动捕捉明显
  问题；更隐蔽的还是要你来盯

## 准备走 mainnet

我们强烈建议**先在 testnet 跑数周**。要切的时候：

1. 设 `GATE_USE_TESTNET=false`
2. 把 `INITIAL_BALANCE_USDT` 调到「亏光也能承受」的金额
3. 在 Gate.io 把 API key 权限设成「仅交易、禁止提现」
4. 走一遍 [G1–G6 验收门](../CLAUDE.md) 再放手不管

如果遇到 FAQ 没覆盖的问题，欢迎
[开 issue](https://github.com/gong1414/omnitrade/issues/new/choose)。
