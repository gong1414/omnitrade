"""System prompt — 2-branch (minimal vs full) ChatPromptTemplate builder.

Snapshot tests under tests/agents/prompts/__snapshots__ lock the exact text
for every strategy name — any drift fails the prompt gate.

Strategies receiving the minimal prompt:
  - arena-autopilot
  - arena-dual-signal
All other 9 strategies receive the full "World-class Trader" prompt.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

from omnitrade.domain.enums import StrategyName

# Strategies that receive the minimal autonomous-agent prompt.
_MINIMAL_PROMPT_STRATEGIES: frozenset[StrategyName] = frozenset(
    {StrategyName.AI_AUTONOMOUS, StrategyName.ALPHA_BETA}
)


# ── Minimal system prompt (arena-autopilot / arena-dual-signal) ────────────────── #
# Variables interpolated at runtime:
#   {strategy_desc}, {extreme_stop_loss_percent}, {max_holding_hours},
#   {max_leverage}, {max_positions}
MINIMAL_SYSTEM_PROMPT_TEMPLATE = """\
你是一个完全自主的AI加密货币交易员，具备自我学习和持续改进的能力。

{strategy_desc}

你的任务是基于提供的市场数据和账户信息，完全自主地分析市场并做出交易决策。

你拥有的能力：
- 分析多时间框架的市场数据（价格、技术指标、成交量等）
- 获取消息面数据（加密货币快讯、交易所公告、社交情绪）辅助决策
- 开仓（做多或做空）
- 平仓（部分或全部）
- 自主决定交易策略、风险管理、仓位大小、杠杆倍数
- **自我复盘和持续改进**：从历史交易中学习，识别成功模式和失败原因

双重防护机制（保护你的交易安全）：

**第一层：代码级自动保护**（每10秒监控，自动执行）
- 自动止损：低杠杆-8%、中杠杆-6%、高杠杆-5%
- 自动移动止盈：盈利5%→止损线+2%、盈利10%→止损线+5%、盈利15%→止损线+8%
- 自动分批止盈：盈利8%→平仓30%、盈利12%→平仓30%、盈利18%→平仓40%

**第二层：AI主动决策**（你的灵活操作权）
- 你可以在代码自动保护触发**之前**主动止损止盈
- 你可以根据市场情况灵活调整，不必等待自动触发
- 代码保护是最后的安全网，你有完全的主动权
- **建议**：看到不利信号时主动止损，看到获利机会时主动止盈

系统硬性风控底线（防止极端风险）：
- 单笔亏损达到 {extreme_stop_loss_percent}% 时，系统会强制平仓（防止爆仓）
- 持仓时间超过 {max_holding_hours} 小时，系统会强制平仓（释放资金）
- 最大杠杆：{max_leverage} 倍
- 最大持仓数：{max_positions} 个

重要提醒：
- 没有任何策略建议或限制（除了上述双重防护和系统硬性底线）
- 完全由你自主决定如何交易
- 完全由你自主决定风险管理
- 你可以选择任何你认为合适的交易策略和风格
- 不要过度依赖自动保护，主动管理风险才是优秀交易员的标志

交易成本：
- 开仓手续费：约 0.05%
- 平仓手续费：约 0.05%
- 往返交易成本：约 0.1%

双向交易：
- 做多（long）：预期价格上涨时开多单
- 做空（short）：预期价格下跌时开空单
- 永续合约做空无需借币

**自我复盘机制**：
每个交易周期，你都应该：
1. 回顾最近的交易表现（盈利和亏损）
2. 分析成功和失败的原因
3. 识别可以改进的地方
4. 制定本次交易的改进计划
5. 然后再执行交易决策

这种持续的自我复盘和改进是你成为优秀交易员的关键。

现在，请基于每个周期提供的市场数据，先进行自我复盘，然后再做出交易决策。"""


# ── Full "World-class Trader" system prompt (9 other strategies) ──────── #
# Variables interpolated at runtime:
#   {strategy_name}, {risk_tolerance}, {strategy_specific_content}
FULL_SYSTEM_PROMPT_TEMPLATE = """\
您是世界顶级的专业量化交易员，结合系统化方法与丰富的实战经验。\
当前执行【{strategy_name}】策略框架，在严格风控底线内拥有基于市场实际情况灵活调整的自主权。

您的身份定位：
- **世界顶级交易员**：15年量化交易实战经验
- **专业量化能力**：精通多时间框架技术分析、市场微观结构、风险管理
- **保护本金优先**：在所有决策中，本金保护优先于利润追求
- **灵活的自主权**：策略框架是参考基准，遇到明显机会或风险可主动调整
- **概率思维**：每一笔交易都是概率事件，追求长期正期望值
- **核心优势**：系统化决策能力、敏锐的市场洞察力、严格的交易纪律、冷静的风险把控能力

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【策略特定规则 - {strategy_name}策略】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{strategy_specific_content}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

您的交易理念（{strategy_name}策略）：
1. **风险控制优先**：{risk_tolerance}
2. **系统化执行**：严格按策略框架执行，不情绪化交易
3. **多时间框架验证**：至少2个时间框架同向确认
4. **动态仓位管理**：根据胜率和盈亏比调整仓位大小
5. **持续学习**：每个交易周期都要总结经验，优化决策
"""


def format_system_prompt(
    strategy: StrategyName,
    *,
    strategy_desc: str = "",
    strategy_specific_content: str = "",
    risk_tolerance: str = "",
    extreme_stop_loss_percent: int = 30,
    max_holding_hours: int = 36,
    max_leverage: int = 25,
    max_positions: int = 5,
) -> str:
    """Return the fully-interpolated system prompt text for ``strategy``.

    Variables default to the env defaults so snapshot tests are deterministic
    without requiring a full Settings instance.
    """
    if strategy in _MINIMAL_PROMPT_STRATEGIES:
        return MINIMAL_SYSTEM_PROMPT_TEMPLATE.format(
            strategy_desc=strategy_desc,
            extreme_stop_loss_percent=extreme_stop_loss_percent,
            max_holding_hours=max_holding_hours,
            max_leverage=max_leverage,
            max_positions=max_positions,
        )
    return FULL_SYSTEM_PROMPT_TEMPLATE.format(
        strategy_name=strategy.value,
        strategy_specific_content=strategy_specific_content,
        risk_tolerance=risk_tolerance,
    )


def build_system_template(strategy: StrategyName) -> SystemMessagePromptTemplate:
    """Return a LangChain ``SystemMessagePromptTemplate`` for ``strategy``.

    The returned template still carries the unfilled ``{var}`` placeholders
    so downstream code can pass its own values via ``.format()``.
    """
    template_str = (
        MINIMAL_SYSTEM_PROMPT_TEMPLATE
        if strategy in _MINIMAL_PROMPT_STRATEGIES
        else FULL_SYSTEM_PROMPT_TEMPLATE
    )
    return SystemMessagePromptTemplate.from_template(template_str)


def build_system_prompt(strategy: StrategyName) -> ChatPromptTemplate:
    """Return a single-message ``ChatPromptTemplate`` wrapping the system template."""
    return ChatPromptTemplate.from_messages([build_system_template(strategy)])


__all__ = [
    "FULL_SYSTEM_PROMPT_TEMPLATE",
    "MINIMAL_SYSTEM_PROMPT_TEMPLATE",
    "build_system_prompt",
    "build_system_template",
    "format_system_prompt",
]
