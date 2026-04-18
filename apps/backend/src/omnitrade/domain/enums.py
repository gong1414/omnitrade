"""Domain enums — shared vocabulary for the trading domain."""

from __future__ import annotations

from enum import StrEnum


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    FORCE_CLOSED = "force_closed"


class ClosePath(StrEnum):
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    PARTIAL_PROFIT = "partial_profit"
    AI_DECISION = "ai_decision"
    NONE = "none"


class StrategyName(StrEnum):
    CONSERVATIVE = "arena-guardian"
    BALANCED = "arena-steward"
    AGGRESSIVE = "arena-raider"
    AGGRESSIVE_TEAM = "arena-raider-squad"
    ULTRA_SHORT = "arena-scalper"
    SWING_TREND = "arena-swingsmith"
    MEDIUM_LONG = "arena-strider"
    REBATE_FARMING = "arena-rebate-hunter"
    AI_AUTONOMOUS = "arena-autopilot"
    MULTI_AGENT_CONSENSUS = "arena-tribunal"
    ALPHA_BETA = "arena-dual-signal"


class Environment(StrEnum):
    TESTNET = "testnet"
    MAINNET = "mainnet"
