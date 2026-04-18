"""TraceContext — correlation-id propagation via ContextVar + Starlette middleware.

Per consensus plan §7 R2 (non-negotiable):
  - X-Correlation-ID header passthrough (use client-supplied value if present)
  - Auto-generate UUID4 when header is missing
  - Bind to structlog processor so every log line carries the id
  - Export get_correlation_id() helper for use outside request context

Phase 1 scope: middleware only. TraceContext dataclass (request_id, decision_id,
trade_id, iteration, strategy, symbol) is defined here as a stub and will be
populated in Phase 3/4 when the trading loop and agent are wired in.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# ── correlation-id contextvar ──────────────────────────────────────────────── #

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the current correlation-id, or empty string outside a request."""
    return correlation_id.get()


# ── TraceContext dataclass (stub — Phase 3/4 will populate all fields) ────── #


@dataclass
class TraceContext:
    """Rich trace context for a single agent decision cycle.

    Populated progressively:
      - request_id: set by TraceContextMiddleware on every HTTP request
      - decision_id: set by trading loop scheduler when a cycle starts
      - trade_id: set by trade-execution tool when an order is placed
      - iteration, strategy, symbol: set by trading loop
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str = ""
    trade_id: str = ""
    iteration: int = 0
    strategy: str = ""
    symbol: str = ""


# ── structlog processor ────────────────────────────────────────────────────── #


def with_context(bound_logger: Any) -> Any:
    """Return logger bound with the current correlation_id.

    Usage::

        with_context(logger).info("some.event", key="value")

    Repositories and services call this on every log statement so the
    bare-logger grep gate (Phase 1.2a) finds zero naked logger.info calls.
    """
    cid = get_correlation_id()
    if cid:
        return bound_logger.bind(correlation_id=cid)
    return bound_logger


def add_correlation_id(
    logger: Any,
    method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor: inject correlation_id into every log record."""
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_structlog() -> None:
    """Configure structlog with JSON renderer + correlation-id processor.

    Call once at application startup (main.py lifespan).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ── Starlette middleware ───────────────────────────────────────────────────── #

_HEADER_NAME = "X-Correlation-ID"


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Extract or generate X-Correlation-ID; bind to ContextVar and structlog."""

    def __init__(self, app: ASGIApp, header_name: str = _HEADER_NAME) -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        # 1. Extract from request header or generate a fresh UUID4
        cid = request.headers.get(self._header_name) or str(uuid.uuid4())

        # 2. Set the ContextVar so downstream code can call get_correlation_id()
        token = correlation_id.set(cid)

        # 3. Bind to structlog contextvars so all log calls in this task carry it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=cid)

        try:
            response: Response = await call_next(request)
        finally:
            # 4. Reset ContextVar (best-effort; asyncio tasks inherit a copy)
            correlation_id.reset(token)
            structlog.contextvars.clear_contextvars()

        # 5. Inject id into response header so clients can correlate logs
        response.headers[self._header_name] = cid
        return response
