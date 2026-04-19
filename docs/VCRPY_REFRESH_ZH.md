<p align="right">
  <a href="./VCRPY_REFRESH.md">English</a> | <b>简体中文</b>
</p>

# OmniTrade —— VCR Cassette 刷新 Runbook

> **已废弃 —— 由 Phase 9 PR-B2 结构化输出契约测试取代。**
>
> 22-cassette 行为等价门及其 VCR 重放基础设施已在 PR-B2 Phase D 中退役。Cassette 目录（`apps/backend/tests/behavioral_equivalence/`）和驱动脚本（`scripts/run_characterization.py`）已从仓库中删除。

## 新回归方案

回归检测现在由 `apps/backend/tests/agents/` 下的结构化输出契约测试套件负责：

- `tests/agents/test_structured_output_contract.py` —— 28 条结构化输出契约断言，覆盖所有决策形态、tool-call schema、hold/close action 类型。
- `tests/agents/test_tool_aware_gate.py` —— Tool-aware gate：验证 `build_hold_tool` 激活及各场景的正确工具选择。
- `scripts/pr_b2_phase_a_probe.py` / `scripts/pr_b2_phase_b_probe.py` —— 漂移检测探针，可在本地对真实 LLM key 运行。

```bash
cd apps/backend
uv run pytest tests/agents/ -q
```

## 历史说明

22-cassette 门（Phase 4.5 – Phase 8）使用由 `_cassette_synth.py` 从手工策展 baseline JSON 确定性合成的 VCR cassette。该门是 characterization 门（≥ 0.95 通过率），不是 byte-exact parity。被取代的原因：

1. Prompt 重写（PR-B2 Phase A）和 `build_hold_tool` 激活（Phase B）后，真实 LLM 响应已与冻结 baseline 分道扬镳。
2. 28 条新结构化测试提供了更直接、更易维护的回归信号，与当前 prompt 契约对齐。

完整理由见 `.omc/plans/prompt-audit-modernization.md` §Step 7。
