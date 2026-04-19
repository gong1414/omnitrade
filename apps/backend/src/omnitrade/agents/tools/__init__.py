"""LangChain tool wrappers exposed to the think node.

Each tool wraps an existing infrastructure adapter (exchange, news, MCP)
and enforces Phase-0 #4 atomicity through the repository's
``apply_three_way_state`` helper where relevant.

The module is scope-gated (§7 R9): no ``langgraph`` imports live here —
only ``langchain_core.tools`` + stdlib/Pydantic.
"""

from __future__ import annotations

from omnitrade.agents.tools.account_management import (
    build_account_snapshot_tool,
    build_check_order_status_tool,
    build_list_positions_tool,
    build_open_orders_tool,
    build_sync_positions_tool,
)
from omnitrade.agents.tools.external_data import build_external_data_tool
from omnitrade.agents.tools.market_data import (
    build_fetch_ohlcv_tool,
    build_fetch_ticker_tool,
    build_funding_rate_tool,
    build_open_interest_tool,
    build_order_book_tool,
)
from omnitrade.agents.tools.news_data import build_news_data_tool
from omnitrade.agents.tools.risk import build_calculate_risk_tool
from omnitrade.agents.tools.trade_execution import (
    build_cancel_order_tool,
    build_close_position_tool,
    build_hold_tool,
    build_open_position_tool,
    build_partial_close_tool,
)

__all__ = [
    "build_account_snapshot_tool",
    "build_calculate_risk_tool",
    "build_cancel_order_tool",
    "build_check_order_status_tool",
    "build_close_position_tool",
    "build_external_data_tool",
    "build_fetch_ohlcv_tool",
    "build_fetch_ticker_tool",
    "build_funding_rate_tool",
    "build_hold_tool",
    "build_list_positions_tool",
    "build_news_data_tool",
    "build_open_interest_tool",
    "build_open_orders_tool",
    "build_open_position_tool",
    "build_order_book_tool",
    "build_partial_close_tool",
    "build_sync_positions_tool",
]
