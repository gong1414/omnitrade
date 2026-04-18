"""LogBuffer — in-process bounded ring buffer for recent structlog events.

Phase 8.3 gives the dashboard a ``GET /api/logs`` endpoint without
adding a log-shipper dependency; a side-car structlog processor forwards
every rendered event into the buffer and ``/api/logs`` tails it.

Design:
- ``collections.deque(maxlen=10_000)`` caps memory (~2 MB at ~200B / row).
- ``threading.Lock`` makes ``append`` / ``tail`` safe for both sync
  (structlog background threads) and the single asyncio event loop.
- Events are plain ``dict`` copies so consumers cannot mutate retained data.
- ``buffer_processor`` is a structlog processor factory so ``configure_structlog``
  can mount it alongside ``JSONRenderer``.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import MutableMapping
from typing import Any

_MAX_EVENTS = 10_000

# ``structlog`` numeric log levels emitted by ``add_log_level``.
_LEVEL_ORDER: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
}


def _level_rank(level: str | None) -> int:
    """Return the numeric rank for a structlog level name (INFO if unknown)."""
    if not level:
        return 20
    return _LEVEL_ORDER.get(level.lower(), 20)


class LogBuffer:
    """Bounded in-memory store of recent log events (10k max).

    Thread-safe: ``append`` is called from structlog's binding thread,
    ``tail`` from the FastAPI event loop. A single ``threading.Lock``
    serialises both sides cheaply.
    """

    def __init__(self, capacity: int = _MAX_EVENTS) -> None:
        self._buf: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.capacity = capacity

    def append(self, event: dict[str, Any]) -> None:
        """Store ``event`` (shallow copy) in the ring buffer."""
        # Shallow-copy so the consumer cannot observe mutations made by
        # downstream structlog processors (JSONRenderer, add_log_level, …).
        snapshot = dict(event)
        with self._lock:
            self._buf.append(snapshot)

    def tail(self, level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """Return the most-recent events, newest-first, filtered by ``level``.

        ``level`` is a structlog level name (``"info"``, ``"warning"`` …).
        Events below the requested threshold are skipped. Unknown level
        strings in stored events default to INFO rank.
        """
        if limit <= 0:
            return []
        threshold = _level_rank(level) if level else 0
        with self._lock:
            # Iterate newest-first to honour ``limit`` cheaply.
            rows: list[dict[str, Any]] = []
            for evt in reversed(self._buf):
                if threshold and _level_rank(str(evt.get("level", ""))) < threshold:
                    continue
                rows.append(dict(evt))
                if len(rows) >= limit:
                    break
        return rows

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


# ── structlog sidecar processor factory ──────────────────────────────── #


def buffer_processor(
    buffer: LogBuffer,
) -> Any:
    """Build a structlog processor that mirrors every event into ``buffer``.

    The processor is pass-through: it returns ``event_dict`` unchanged so
    the downstream JSONRenderer keeps working.
    """

    def _processor(
        _logger: Any,
        _method: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        # dict() copy preserves the event before later processors mutate it.
        buffer.append(dict(event_dict))
        return event_dict

    return _processor


__all__ = ["LogBuffer", "buffer_processor"]
