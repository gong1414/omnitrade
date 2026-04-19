"""CachedLLMClient — sqlite-backed response cache around any ``LLMClient``.

Purpose
-------
Backtest replays are deterministic in their market inputs (historical
OHLCV) but the LLM call itself is non-deterministic and expensive. By
hashing the request ``(messages, model, temperature, tools,
tool_choice)`` and storing the response under that key, subsequent
backtests over the same candles skip the network hop entirely — every
cycle becomes a disk read.

Determinism contract
--------------------
The cache key is ``sha256(json.dumps(..., sort_keys=True))`` so any
floating-point / dict-order drift in the request body produces the
same key. Callers must feed ``temperature=0`` for byte-exact replays;
otherwise a different trial invalidates the key.

Schema
------
Single table ``llm_cache(cache_key PRIMARY KEY, response_json, created_at)``.
No schema migrations — the DB is append-only and recreated by deleting
``.backtest/llm_cache.db``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog

from omnitrade.domain.protocols import LLMClient

logger = structlog.get_logger(__name__)


class CachedLLMClient:
    """Wrap any ``LLMClient`` with an sqlite cache keyed on the full request.

    Args:
        inner: The real LLM client. Called on cache miss.
        cache_path: Path to the sqlite DB. Parent dirs are created.
        use_cache: When False, every call hits the inner client and
            the response is STILL stored — useful for "warm the cache
            on a single real run then replay N backtests".
    """

    def __init__(
        self,
        inner: LLMClient,
        cache_path: Path | str,
        *,
        use_cache: bool = True,
    ) -> None:
        self._inner = inner
        self._path = Path(cache_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._use_cache = use_cache
        # sqlite3 connection is not thread-safe by default; the backtest
        # engine is single-task asyncio so a lock around write is enough.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "cache_key TEXT PRIMARY KEY, "
            "response_json TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self._conn.commit()

        # Counters exposed for test / CLI observability.
        self.hits: int = 0
        self.misses: int = 0

    # ── key ──────────────────────────────────────────────────────────── #

    @staticmethod
    def _compute_key(
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
    ) -> str:
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        body = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    # ── cache IO ─────────────────────────────────────────────────────── #

    def _lookup(self, key: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT response_json FROM llm_cache WHERE cache_key = ?", (key,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        assert isinstance(data, dict)
        return data

    def _store(self, key: str, response: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache"
                " (cache_key, response_json, created_at) VALUES (?, ?, ?)",
                (
                    key,
                    json.dumps(response, default=str),
                    datetime.now(tz=UTC).isoformat(),
                ),
            )
            self._conn.commit()

    # ── public surface (LLMClient protocol) ──────────────────────────── #

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "required", "none"] | None = None,
    ) -> dict[str, Any]:
        key = self._compute_key(messages, model, temperature, tools, tool_choice)
        if self._use_cache:
            cached = self._lookup(key)
            if cached is not None:
                self.hits += 1
                logger.info("llm_cache.hit", key=key[:8], total_hits=self.hits)
                return cached
        resp = await self._inner.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
        )
        self.misses += 1
        logger.info("llm_cache.miss", key=key[:8], total_misses=self.misses)
        self._store(key, resp)
        return resp

    def close(self) -> None:
        """Close the underlying sqlite connection (safe to call twice)."""
        try:
            self._conn.close()
        except Exception:
            pass


# Type alias used by the engine: the ``CachedLLMClient`` fully implements
# the ``LLMClient`` Protocol (structural; no explicit inheritance needed).
LLMClientFactory = Callable[[], Awaitable[LLMClient]]


__all__ = ["CachedLLMClient"]
