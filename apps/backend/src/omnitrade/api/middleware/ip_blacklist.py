"""IPBlacklistMiddleware — rejects requests from blacklisted IPs.

Reads the comma-separated ``IP_BLACKLIST`` environment variable at construction
time (or accepts an explicit allow-list-override via the constructor for
tests). An incoming request from a listed IP returns HTTP 403 without
entering any route handler.
"""

from __future__ import annotations

import os

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)


def _parse_env(value: str | None) -> set[str]:
    if not value:
        return set()
    return {ip.strip() for ip in value.split(",") if ip.strip()}


class IPBlacklistMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``request.client.host`` is in the blacklist."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        blacklist: set[str] | None = None,
        env_var: str = "IP_BLACKLIST",
    ) -> None:
        super().__init__(app)
        if blacklist is not None:
            self._blacklist = set(blacklist)
        else:
            self._blacklist = _parse_env(os.environ.get(env_var))

    @property
    def blacklist(self) -> frozenset[str]:
        return frozenset(self._blacklist)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client = request.client
        client_ip = client.host if client else ""
        if client_ip and client_ip in self._blacklist:
            with_context(logger).warning(
                "ip_blacklist.blocked",
                client_ip=client_ip,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "forbidden"},
            )
        return await call_next(request)


__all__ = ["IPBlacklistMiddleware"]
