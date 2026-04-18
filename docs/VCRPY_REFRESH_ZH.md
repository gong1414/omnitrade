<p align="right">
  <a href="./VCRPY_REFRESH.md">English</a> | <b>简体中文</b>
</p>

# OmniTrade —— VCR Cassette 刷新 Runbook

> 当 LLM provider 的 API 形态变了，已录制的 VCR cassette 就对不上实际响应，行为等价门开始出现假阴性。本文档说明**什么时候**刷新 cassette、**怎么**刷新，并保证不泄漏 secret。
>
> 本门是 **characterization**，不是 byte-exact parity；详情见 `.omc/plans/phase-8-oracle-spike-report.md`。

---

## 1. 什么时候刷新

**只有**以下情形才应刷新 cassette：

1. **LLM provider 改了响应 schema** —— 例如 DeepSeek 加了新字段 `reasoning`、OpenAI 兼容 provider 调整了 `choices[].message.content` 形状、tool-call 封装从 `function_call` 迁到 `tool_calls`。
2. **模型升级** —— 升 `LLM_MODEL_NAME`（如 `deepseek-v3.2-exp → deepseek-v4`），新模型语义不同但仍需过等价门。
3. **Provider 切换** —— 从 DeepSeek 换到 OpenRouter / native OpenAI / Claude；cassette 包含 provider 特有 header，vcrpy 靠这些做匹配。
4. **新增 fixture** —— 引入第 23 份 `tests/fixtures/frozen/` snapshot 时，必须先录对应 cassette，行为等价门才会过。

**不要**因为以下情况刷新：

- 单个测试 flaky（先排查测试）
- 等价门刚好低于 0.95（先查决策 diff）
- 网络抖动（重试即可 —— cassette 就是为了消除这个）

如果通过率回归但查不出 LLM API 改动，在 Issue 里打 `characterization-regression` 标签，**不要**刷新。静默刷新会掩盖真实的行为漂移。

---

## 2. 前置条件

- 一个**有效 API key**，额度够 22 次重放（每份 fixture ~20k token，共 ~450k token）。
- `tests/fixtures/frozen/market_snapshots/` 和 `tests/fixtures/frozen/baseline_decisions/` 下的 fixture**不动**（它们是 ground truth，只有 cassette 刷新）。
- 干净的 git 工作树，cassette diff 才好审阅。
- `uv` 在 PATH 里、`apps/backend/.venv/` 已同步（`cd apps/backend && uv sync --all-extras`）。
- `VCR_RECORD_MODE=once` —— 缺的交互才录，已存在的不覆盖。真要整体换才用 `all`。

API key 放到 **不进 git** 的文件：

```bash
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL_NAME="deepseek/deepseek-v3.2-exp"
```

---

## 3. 流程

### 3.1 备份已有 cassette

```bash
cd apps/backend/tests/behavioral_equivalence
cp -R cassettes cassettes.bak-$(date +%Y%m%d)
ls cassettes.bak-*/ | wc -l        # 数量应与 cassettes/ 一致
cd ../../../..
```

### 3.2 删除要刷新的 cassette

单份 fixture：

```bash
rm apps/backend/tests/behavioral_equivalence/cassettes/case_13_autopilot_close_full.yaml
```

全量（罕见）：

```bash
rm apps/backend/tests/behavioral_equivalence/cassettes/case_*.yaml
```

**不要**删 `_smoke_roundtrip.yaml`，除非 smoke 本身挂了。

### 3.3 对着真 API 重新录制

`VCR_RECORD_MODE=once` 下行为等价测试会录所有被删掉的 cassette，其他已存在的原样回放：

```bash
cd apps/backend
VCR_RECORD_MODE=once uv run pytest tests/behavioral_equivalence/test_decision_characterization.py -q
```

预期：被删掉的 cassette 会重建；其他 cassette 从磁盘回放。已存在的不发网络请求。

### 3.4 审阅 diff

```bash
git diff -- apps/backend/tests/behavioral_equivalence/cassettes/
```

**可接受**（语义变化）：

- 响应 body 里新增字段（如 `usage.reasoning_tokens`）
- JSON key 顺序变化（YAML 会规范化，但模型可能重排）
- 更新的 model 版本字符串
- provider 新加的 `tool_calls` 封装

**要拒绝并排查**：

- 决策文本完全变了（`buy` → `sell` 等）—— 真实行为漂移
- 响应 body 为空 / 截断 —— 录制时限流或部分失败
- 测试断言的 header 变化

### 3.5 验证行为等价门

```bash
cd ../..
uv --project apps/backend run python scripts/run_characterization.py \
  --fixtures tests/fixtures/frozen/ \
  --cassettes apps/backend/tests/behavioral_equivalence/cassettes/ \
  --threshold 0.95 \
  --report apps/backend/tests/behavioral_equivalence/reports/refresh-check.json
```

通过率 ≥ 0.95 才提交。否则**不要** commit —— 回滚（`rm -rf apps/backend/tests/behavioral_equivalence/cassettes && mv cassettes.bak-* cassettes`）并开一个 regression issue。

### 3.6 提交

```bash
git add apps/backend/tests/behavioral_equivalence/cassettes/
git commit -m "chore(characterization): refresh cassettes for <provider/model 原因>"
```

Cassette 刷新必须是原子 commit，不要和源码改动混在一起。

### 3.7 验证通过后删备份

```bash
rm -rf apps/backend/tests/behavioral_equivalence/cassettes.bak-*
```

---

## 4. 安全：严禁 commit secret

`conftest.py` 配置了 vcrpy 的过滤器，在 cassette 持久化前剥掉敏感 header。提交前再 double-check：

```bash
rg -i 'authorization|api[-_]?key|bearer|sk-[A-Za-z0-9]+' \
   apps/backend/tests/behavioral_equivalence/cassettes/
# 预期：空
```

只要有命中，**立即停止**。不要 `git commit`。在 `conftest.py` 的 `filter_headers` 列表里加上泄漏的 header 名，删掉被污染的 cassette，重新走 §3。

`conftest.py` 里必须保留的最小过滤集：

```python
my_vcr = vcr.VCR(
    filter_headers=[
        "authorization",
        "x-api-key",
        "openai-api-key",
        "cookie",
        "set-cookie",
    ],
    filter_query_parameters=["api_key", "token"],
    filter_post_data_parameters=["api_key"],
)
```

顺便确认 YAML 里没有明文 bearer token：

```bash
rg -n 'Bearer sk-' apps/backend/tests/behavioral_equivalence/cassettes/
# 预期：空
```

---

## 5. 进阶：单 interaction 刷新

如果 cassette 里只有某一次交互改了（例如 `case_14_autopilot_close_partial.yaml` 里 3 次 LLM 调用中的一次），可以手改 YAML —— cassette 是纯文本。改完务必 `yamllint` 校验、replay 过再 commit：

```bash
yamllint apps/backend/tests/behavioral_equivalence/cassettes/case_14_*.yaml
uv --project apps/backend run pytest tests/behavioral_equivalence/test_cassette_roundtrip.py -k case_14 -q
```

---

## 6. 排错

| 现象 | 原因 | 修复 |
|---|---|---|
| `CannotOverwriteExistingCassetteException` | 在 `record_mode=once` 下，cassette 还存在时就想覆盖 | 先按 §3.2 删，再重录 |
| `<fixture>.yaml` 录完是空的 | 录制机网络被挡 | 延长超时；确保 HTTPS 出口放开 |
| 行为等价门通过率从 1.00 → 0.93 | 模型更新改了决策文本 | 接受（更新 baseline）或回滚 |
| cassette 里混进了 secret | `conftest.py` 缺过滤器 | 加进 `filter_headers`；删 cassette 重录 |

---

## 7. 行为等价门 spike 备忘（2026-04-18）

- **结论：** byte-exact v2 baseline 不可行 —— 本门是 **characterization**，不是 parity。
- **证据：** 见 `.omc/plans/phase-8-oracle-spike-report.md`。

22 份 `tests/fixtures/frozen/baseline_decisions/case_NN_*.json` 是手工策展契约（人工散文 `notes`、手工算术、`EDGE CASE` 标记、无 provenance 字段、无原始 LLM 字节）。其中 ~59%（13/22 个 monitor 触发的平仓：`trailing_stop` / `stop_loss` / `partial_profit`）按架构就不会调 LLM —— LLM 层根本没东西可重放。`apps/backend/tests/behavioral_equivalence/_cassette_synth.py` 明确说 cassette 是从 baseline JSON 确定性合成（"pure — no network"）。因此 22/22 门锁的是 Python 端相对固化手工契约的回归。本 runbook 的核心 VCR 流程在 Python 端的 LLM provider 契约漂移时仍然适用。
