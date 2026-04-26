"""Knowledge / RAG layer for the trading agent (T10).

Exposes :func:`build_trade_journal_knowledge` (factory) and
:func:`record_decision_to_knowledge` (post-cycle ingest helper).

When ``settings.agno_postgres_url`` is unset (test path, DB-less local
dev) the factory is a no-op — match the T2 / T4 "Postgres present →
enable; absent → graceful skip" pattern.
"""

from __future__ import annotations

from omnitrade.agents.knowledge.trade_journal import (
    build_trade_journal_knowledge,
    record_decision_to_knowledge,
    serialise_decision_for_journal,
)

__all__ = [
    "build_trade_journal_knowledge",
    "record_decision_to_knowledge",
    "serialise_decision_for_journal",
]
