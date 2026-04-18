"""Loop registry — name → callable + interval mapping.

Exposed to Phase 5 application layer for dynamic loop management.
Each entry defines the job name, default interval, and stub callable.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoopSpec:
    """Specification for a single scheduler loop."""

    name: str
    interval_seconds: float
    callable: Callable[[], Coroutine[Any, Any, None]]
    description: str


# Registry is populated by OmniScheduler at startup.
# Phase 5 can read this to list active loops or adjust intervals dynamically.
_registry: dict[str, LoopSpec] = {}


def register(spec: LoopSpec) -> None:
    """Register a loop spec (called by OmniScheduler)."""
    _registry[spec.name] = spec


def get_all() -> dict[str, LoopSpec]:
    """Return a copy of the current loop registry."""
    return dict(_registry)


def get(name: str) -> LoopSpec | None:
    """Return a loop spec by name, or None if not registered."""
    return _registry.get(name)
