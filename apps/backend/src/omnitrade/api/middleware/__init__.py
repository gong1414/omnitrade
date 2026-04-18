"""API middleware package."""

from omnitrade.api.middleware.ip_blacklist import IPBlacklistMiddleware

__all__ = ["IPBlacklistMiddleware"]
