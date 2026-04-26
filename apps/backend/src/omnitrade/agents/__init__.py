"""Agents layer — Agno-based trading agent + advisory team.

The production think path is :mod:`omnitrade.agents.trading_agent` (a
single Agno ``Agent`` driving DeepSeek with MultiMCPTools). When
``MULTI_AGENT_ENABLED`` is set with a team-eligible strategy, the
``Team`` defined in :mod:`omnitrade.agents.experts_team` runs first and
its verdict is injected as advisory context — the Agent remains the
sole producer of the final ``Decision``. The outer trading loop lives
at ``application/trading_loop.py`` as pure asyncio with no LLM imports.
"""
