"""Multi-agent orchestrator error types (Phase 8.5a).

``MultiAgentDegradedError`` is raised when a sub-agent (team expert or
consensus juror) fails — most commonly via ``asyncio.wait_for`` timeout
against ``settings.expert_timeout_seconds``. The WS ``/ws/stream``
endpoint surfaces this to the frontend ``ConnectionBanner`` as an
``orchestrator_error`` envelope (plan v3 G-5).
"""

from __future__ import annotations


class MultiAgentDegradedError(Exception):
    """Raised when a multi-agent sub-agent fails or times out.

    Attributes:
        strategy: The active ``StrategyName`` value (e.g. ``"arena-raider-squad"``).
        reason: Human-readable cause (e.g. ``"trendExpert timeout after 15s"``).
        correlation_id: The correlation id propagated from the main agent call
            so dashboards can stitch logs across the orchestrator boundary.
    """

    def __init__(self, *, strategy: str, reason: str, correlation_id: str) -> None:
        self.strategy = strategy
        self.reason = reason
        self.correlation_id = correlation_id
        super().__init__(f"multi_agent_degraded: strategy={strategy} reason={reason}")


__all__ = ["MultiAgentDegradedError"]
