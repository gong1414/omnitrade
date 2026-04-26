"""T10 — Trade-journal RAG via Agno :class:`Knowledge` + :class:`PgVector`.

Every cycle, after the :class:`StructuredReason` is emitted and the
:class:`AgentDecision` row is persisted, we serialise the decision into a
short natural-language summary and ingest it as a knowledge document. On
the next cycle Agno's ``search_knowledge=True`` injects the most semantically
relevant previous decisions back into the system prompt — the LLM gains a
"what did I decide last time the market looked similar?" memory layer.

Design / failure-mode contract
------------------------------

* **Factory** :func:`build_trade_journal_knowledge` — returns a
  :class:`Knowledge` instance when ``settings.agno_postgres_url`` is wired
  AND the embedder dependency is available, else ``None`` (info-log skip).
  Mirrors the T4 :func:`observability.tracing.setup_tracing` skip pattern.

* **Ingest** :func:`record_decision_to_knowledge` — fire-and-forget. Any
  failure (PgVector down, embedder rate-limited, schema drift) is logged
  and swallowed. NEVER blocks the main cycle. Callers should wrap the
  invocation in :func:`asyncio.create_task` so the cycle return path
  doesn't await the embedding round-trip.

* **Embedder** — Agno's default :class:`OpenAIEmbedder`
  (``text-embedding-3-small``, 1536 dimensions). Reads ``OPENAI_API_KEY``
  via the OpenAI SDK. When the env var is missing we skip with a clear
  warning — the cycle still runs without RAG memory.

* **Schema** — PgVector lives in the ``ai`` schema (Agno default) under
  ``trade_journal`` table. The pgvector PostgreSQL extension must be
  enabled separately; alembic revision ``0006_create_pgvector_extension``
  runs ``CREATE EXTENSION IF NOT EXISTS vector`` (idempotent).

* **Search type** — ``hybrid`` (vector + full-text). The trading agent's
  queries mix concrete numeric signals ("BTC at 67k EMA20 above")
  against narrative phrases ("invalidation triggered last cycle"); the
  hybrid path catches both shapes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from omnitrade.config import Settings

logger = structlog.get_logger(__name__)

# Table name for the trade-journal knowledge documents. Lives in the
# ``ai`` schema (Agno's default for VectorDb tables) so it sits beside
# ``ai.agno_sessions``, ``ai.traces`` etc.
_TABLE_NAME = "trade_journal"

# Soft cap on the natural-language summary length. PgVector's content
# column is ``TEXT`` so there's no hard limit, but the embedder bills /
# rate-limits per token. Most StructuredReasons fit comfortably under
# this; oversize justifications are truncated rather than dropped so the
# semantic core (market context + gates + plan) always lands.
_MAX_CONTENT_CHARS = 4_000


def _build_embedder(settings: Settings, provider: str) -> Any | None:
    """Construct the configured embedder. ``None`` when unbuildable.

    ``fastembed`` is the safe default — runs CPU-bound, no API key.
    ``openai`` routes through Agno's :class:`OpenAIEmbedder` against the
    configured (or LLM-fallback) base URL + key. Any failure logs a
    structured warning and returns ``None`` so the caller can short-circuit
    the whole RAG layer rather than crash the cycle.
    """
    if provider == "fastembed":
        try:
            from agno.knowledge.embedder.fastembed import FastEmbedEmbedder
        except ImportError as exc:
            logger.warning(
                "trade_journal.build.embedder_unavailable",
                provider=provider,
                error=str(exc),
                hint="install `fastembed` — pinned in apps/backend/pyproject.toml",
            )
            return None
        try:
            return FastEmbedEmbedder(id=settings.embedder_model_id)
        except Exception as exc:  # pragma: no cover — best-effort
            logger.warning(
                "trade_journal.build.embedder_failed",
                provider=provider,
                error=str(exc),
            )
            return None

    if provider == "openai":
        embedder_key_secret = settings.embedder_api_key or settings.llm_api_key
        api_key = (
            embedder_key_secret.get_secret_value()
            if embedder_key_secret is not None
            else None
        )
        if not api_key:
            logger.warning(
                "trade_journal.build.skip",
                reason="embedder_api_key/llm_api_key unset",
                hint=(
                    "set EMBEDDER_API_KEY or LLM_API_KEY to enable the "
                    "OpenAI-protocol embedder; the trading cycle still "
                    "runs without it"
                ),
            )
            return None
        embedder_base_raw = settings.embedder_base_url or settings.llm_base_url
        base_url = str(embedder_base_raw) if embedder_base_raw is not None else None
        try:
            from agno.knowledge.embedder.openai import OpenAIEmbedder
        except ImportError as exc:
            logger.warning(
                "trade_journal.build.embedder_unavailable",
                provider=provider,
                error=str(exc),
            )
            return None
        kwargs: dict[str, Any] = {"id": settings.embedder_model_id, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        try:
            return OpenAIEmbedder(**kwargs)
        except Exception as exc:  # pragma: no cover — best-effort
            logger.warning(
                "trade_journal.build.embedder_failed",
                provider=provider,
                error=str(exc),
            )
            return None

    logger.warning(
        "trade_journal.build.unknown_provider",
        provider=provider,
        hint="set EMBEDDER_PROVIDER to one of: fastembed, openai",
    )
    return None


def build_trade_journal_knowledge(settings: Settings) -> Any | None:
    """Construct an Agno :class:`Knowledge` instance backed by PgVector.

    Returns ``None`` (with an info-level skip log) when:

      * ``settings.agno_postgres_url`` is unset — DB-less / test path.
      * Agno's ``Knowledge`` / ``PgVector`` imports fail (missing
        ``pgvector`` extras, rare).
      * The default OpenAI embedder is unusable because
        ``OPENAI_API_KEY`` is unset and the operator hasn't supplied an
        alternative — we'd rather skip RAG than crash the cycle.

    On success the returned instance is wired into the trading Agent via
    ``Agent(knowledge=..., search_knowledge=True)`` so Agno auto-injects
    the most relevant previous decisions on every run.
    """
    if not settings.agno_postgres_url:
        logger.info(
            "trade_journal.build.skip",
            reason="agno_postgres_url unset",
        )
        return None

    provider = (settings.embedder_provider or "fastembed").lower()

    try:
        from agno.knowledge.knowledge import Knowledge
        from agno.vectordb.pgvector import PgVector
        from agno.vectordb.search import SearchType
    except ImportError as exc:
        logger.warning(
            "trade_journal.build.import_failed",
            error=str(exc),
            hint=(
                "install `pgvector` (Python client) — pinned in "
                "apps/backend/pyproject.toml"
            ),
        )
        return None

    embedder = _build_embedder(settings, provider)
    if embedder is None:
        return None

    try:
        vector_db = PgVector(
            table_name=_TABLE_NAME,
            db_url=settings.agno_postgres_url,
            search_type=SearchType.hybrid,
            embedder=embedder,
        )
        knowledge = Knowledge(
            name="trade_journal",
            description=(
                "Per-cycle trade decisions (StructuredReason summaries). "
                "Semantically searchable so the agent can recall similar "
                "market regimes from prior cycles."
            ),
            vector_db=vector_db,
        )
    except Exception as exc:  # pragma: no cover — best-effort wiring
        logger.warning(
            "trade_journal.build.failed",
            error=str(exc),
        )
        return None

    logger.info(
        "trade_journal.build",
        table=_TABLE_NAME,
        host=settings.agno_postgres_url.split("@", 1)[-1].split("/", 1)[0],
        search_type="hybrid",
    )
    return knowledge


def serialise_decision_for_journal(
    structured_reason: Any,
    *,
    run_id: str,
    timestamp: datetime,
) -> tuple[str, dict[str, Any]]:
    """Render a StructuredReason / Decision into ``(content, metadata)``.

    ``content`` is a compact natural-language summary suitable for an
    embedder (market_context + gates + plan + outcome). ``metadata`` is a
    dict of structured filters the LLM can use to narrow searches in
    later cycles (action, confidence, run_id, timestamp).

    Accepts either a :class:`StructuredReason` or a domain
    :class:`Decision` — both expose the same minimal surface
    (``market_context`` / ``gates_passed`` / ``invalidation_condition``
    / ``plan`` / ``confidence`` / ``justification``).
    """
    market_context = (getattr(structured_reason, "market_context", None) or "").strip()
    invalidation = (
        getattr(structured_reason, "invalidation_condition", None) or ""
    ).strip()
    gates: list[str] = list(getattr(structured_reason, "gates_passed", None) or [])
    justification = (getattr(structured_reason, "justification", None) or "").strip()

    # Plan can be either a PlanBlock pydantic model or a dict already
    # (the persistence path stores ``Decision.plan`` as ``dict[str, Any]``).
    plan_raw = getattr(structured_reason, "plan", None)
    if plan_raw is None:
        plan_dict: dict[str, Any] | None = None
    elif isinstance(plan_raw, dict):
        plan_dict = plan_raw
    elif hasattr(plan_raw, "model_dump"):
        plan_dict = plan_raw.model_dump()
    else:
        plan_dict = None

    # Confidence — StructuredReason uses ``confidence``; the domain
    # Decision exposes both ``confidence`` and ``structured_confidence``.
    # Prefer the structured float when present.
    structured_conf = getattr(structured_reason, "structured_confidence", None)
    raw_conf = getattr(structured_reason, "confidence", None)
    confidence_val: float | None
    try:
        if structured_conf is not None:
            confidence_val = float(structured_conf)
        elif raw_conf is not None:
            confidence_val = float(raw_conf)
        else:
            confidence_val = None
    except (TypeError, ValueError):
        confidence_val = None

    action = str(getattr(structured_reason, "action", "") or "")

    # Build the content body. Each section is optional so partial
    # StructuredReasons (e.g. hold with no plan) still produce a useful
    # document.
    sections: list[str] = []
    sections.append(f"Cycle run_id={run_id} at {timestamp.isoformat()}")
    if action:
        sections.append(f"Action: {action}")
    if confidence_val is not None:
        sections.append(f"Confidence: {confidence_val:.2f}")
    if market_context:
        sections.append(f"Market context: {market_context}")
    if gates:
        sections.append("Gates passed:\n  - " + "\n  - ".join(gates))
    if invalidation:
        sections.append(f"Invalidation condition: {invalidation}")
    if plan_dict:
        plan_blob = json.dumps(plan_dict, default=str, sort_keys=True)
        sections.append(f"Plan: {plan_blob}")
    if justification:
        sections.append(f"Justification: {justification}")

    content = "\n\n".join(sections)
    if len(content) > _MAX_CONTENT_CHARS:
        content = content[: _MAX_CONTENT_CHARS - 16] + "\n[...truncated]"

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": timestamp.isoformat(),
        "action": action or None,
        "confidence": confidence_val,
    }

    return content, metadata


async def record_decision_to_knowledge(
    knowledge: Any | None,
    structured_reason: Any,
    *,
    run_id: str,
    timestamp: datetime,
) -> None:
    """Ingest a decision into the trade-journal knowledge base.

    Fire-and-forget contract: any failure is logged and swallowed. The
    caller is expected to wrap this in :func:`asyncio.create_task` so the
    cycle return path doesn't await the embedder round-trip.

    A ``None`` ``knowledge`` short-circuits silently — that's the
    intended behaviour when the factory skipped (Postgres unset,
    OPENAI_API_KEY missing, etc.).
    """
    if knowledge is None:
        return

    try:
        content, metadata = serialise_decision_for_journal(
            structured_reason,
            run_id=run_id,
            timestamp=timestamp,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "trade_journal.record.serialise_failed",
            error=str(exc),
        )
        return

    if not content.strip():
        logger.info(
            "trade_journal.record.skip",
            reason="empty content",
            run_id=run_id,
        )
        return

    name = f"cycle-{run_id}"
    try:
        await knowledge.add_content_async(
            name=name,
            text_content=content,
            metadata=metadata,
        )
    except Exception as exc:
        # Embedder rate-limit, PgVector down, schema drift — none of
        # these should kill the cycle. Log + drop.
        logger.warning(
            "trade_journal.record.failed",
            error=str(exc),
            run_id=run_id,
        )
        return

    logger.info(
        "trade_journal.record",
        run_id=run_id,
        action=metadata.get("action"),
        confidence=metadata.get("confidence"),
        content_chars=len(content),
    )


__all__ = [
    "build_trade_journal_knowledge",
    "record_decision_to_knowledge",
    "serialise_decision_for_journal",
]
