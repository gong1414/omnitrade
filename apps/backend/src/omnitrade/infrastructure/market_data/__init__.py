"""Market-data infrastructure — multi-timeframe fetcher + TTL cache.

Phase 8.1 adds a per-cycle multi-timeframe fetcher guarded by an
``asyncio.Semaphore`` (rate guard) and a per-TF TTL cache that mirrors
the upstream bot's timeframe cadence:

* 1m / 3m / 5m   → 30s  TTL
* 15m / 30m / 1h → 60s  TTL
* 4h / 1d        → 300s TTL

The fetcher is wired into the ``ThinkFn`` chain via
``application.multi_agent.composition.build_think_fn``.
"""

from __future__ import annotations

from omnitrade.infrastructure.market_data.multi_timeframe import MultiTimeframeFetcher
from omnitrade.infrastructure.market_data.tf_cache import InMemoryTTLCache

__all__ = ["InMemoryTTLCache", "MultiTimeframeFetcher"]
