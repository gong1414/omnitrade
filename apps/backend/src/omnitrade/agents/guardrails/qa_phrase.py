"""G5 QA-phrase guardrail — auto-light the dashboard banner on suspect output.

CLAUDE.md Gate G5 says: if the trading Agent's reasoning text contains any
of a known set of fault phrases ("phantom positions", "data sync issue",
"系统异常", …), treat that as a BUG TICKET, not LLM noise. Until now the
gate was a manual eyeball check during release verification — easy to skip,
easy to miss. This module turns it into an automated runtime guardrail:

* :func:`scan_for_qa_phrase` walks a body of text and returns the first
  matching phrase plus a ±60-char snippet so the dashboard has enough
  context to show the operator *why* the banner lit.
* :func:`build_qa_phrase_post_hook` returns an Agno-compatible async
  ``post_hook`` callable that the production trading Agent (see
  :mod:`omnitrade.agents.trading_agent`) hands to the ``Agent``
  constructor via ``post_hooks=[…]``. After every cycle Agno hands the
  hook the freshly-written :class:`agno.run.agent.RunOutput`; the hook
  scans ``run_output.content`` and — on hit — publishes one
  :data:`omnitrade.application.events.bus.EVENT_ORCHESTRATOR_ERROR`
  event so SSE subscribers (the dashboard banner) light up immediately.

The hook deduplicates within a single run: even when the LLM strings
together "数据异常 — 所有 X 都是 0" (two phrases) only the first match
fires. This keeps the banner from stuttering when one cycle's reasoning
contains many fault markers; one cycle = one signal.

Failure-mode contract
---------------------
Hook failures must NEVER abort the cycle. Agno's
``aexecute_post_hooks`` already swallows generic exceptions and logs
them, but we additionally guard the publish call so a flaky event-bus
subscriber can't surface as a guardrail crash.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import structlog

from omnitrade.application.events.bus import EVENT_ORCHESTRATOR_ERROR
from omnitrade.observability.trace_context import with_context

if TYPE_CHECKING:
    from omnitrade.application.events.bus import EventBus

logger = structlog.get_logger(__name__)


# Literal phrase fragments — copied verbatim from CLAUDE.md "Gate G5".
# Order matters only for telemetry: the first hit wins, so we list the
# most diagnostic phrases first ("phantom" was the literal Phase-C bug).
_LITERAL_PHRASES: tuple[str, ...] = (
    # Chinese
    "数据同步故障",
    "系统异常",
    "数据异常",
    "不正常",
    "不符合",
    "异常",
    "错误",
    # English (matched case-insensitively below).
    "phantom",
    "data sync issue",
    "system issue",
    "malformed",
    "inconsistent",
    "anomaly",
    "error",
)

# Compound regex patterns — these correspond to the "所有 X 都是 0" /
# "all X are 0/null/empty" sketches in CLAUDE.md. Both are anchored on
# fragments rather than exact phrases because the LLM fills in the X
# (e.g. "所有持仓数都是 0", "all positions are null"). ASCII patterns
# are case-insensitive; Chinese substring matching is literal.
_COMPOUND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "所有 X 都是 0",
        # 所有 ... 都是 0 — non-greedy filler, allow up to ~30 chars between
        # to keep matches scoped to a single clause.
        re.compile(r"所有[^。\n]{0,30}?都是\s*0"),
    ),
    (
        "all X are 0/null/empty",
        re.compile(r"\ball\b[^.\n]{0,30}?\bare\s+(?:0|null|empty)\b", re.IGNORECASE),
    ),
)


def _find_literal(text: str) -> tuple[str, int] | None:
    """Return ``(phrase, start_index)`` for the earliest literal phrase hit."""
    lower = text.lower()
    best: tuple[str, int] | None = None
    for phrase in _LITERAL_PHRASES:
        # English phrases match case-insensitively; the LITERAL_PHRASES list
        # above is already lowercase for the ASCII entries, so a single
        # ``find`` on the lowercased text is correct for both alphabets.
        idx = lower.find(phrase.lower())
        if idx == -1:
            continue
        if best is None or idx < best[1]:
            best = (phrase, idx)
    return best


def _find_compound(text: str) -> tuple[str, int] | None:
    """Return ``(label, start_index)`` for the earliest compound-pattern hit."""
    best: tuple[str, int] | None = None
    for label, pattern in _COMPOUND_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        if best is None or match.start() < best[1]:
            best = (label, match.start())
    return best


def _snippet(text: str, start: int, phrase: str, *, window: int = 60) -> str:
    """Return ±``window`` chars around ``[start, start+len(phrase))``.

    Adds ellipses on each side when we're not flush against the boundary
    so the dashboard banner can show "…the AI said 系统异常 because…"
    without false-implying it was the entire output.
    """
    end = start + len(phrase)
    left = max(0, start - window)
    right = min(len(text), end + window)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


def scan_for_qa_phrase(text: str) -> tuple[str, str] | None:
    """Return ``(matched_phrase, snippet)`` for the earliest hit, else ``None``.

    The earliest hit wins so a hook deduplicates naturally — we never
    publish more than one orchestrator-error per cycle even when the
    LLM strings several fault phrases together.
    """
    if not text:
        return None

    literal = _find_literal(text)
    compound = _find_compound(text)

    candidates = [c for c in (literal, compound) if c is not None]
    if not candidates:
        return None

    phrase, start = min(candidates, key=lambda hit: hit[1])
    return phrase, _snippet(text, start, phrase)


PostHook = Callable[..., Coroutine[Any, Any, None]]


def build_qa_phrase_post_hook(event_bus: EventBus) -> PostHook:
    """Build an Agno-compatible async post_hook bound to ``event_bus``.

    The returned coroutine accepts arbitrary ``**kwargs`` so it survives
    ``agno.utils.hooks.filter_hook_args`` regardless of which named slots
    Agno injects in any given release; we only read ``run_output``.
    """

    async def qa_phrase_post_hook(**kwargs: Any) -> None:
        run_output = kwargs.get("run_output")
        if run_output is None:
            return
        content = getattr(run_output, "content", None)
        if not isinstance(content, str) or not content:
            return

        hit = scan_for_qa_phrase(content)
        if hit is None:
            return
        phrase, snippet = hit

        payload: dict[str, Any] = {
            "reason": "qa_phrase_match",
            "phrase": phrase,
            "snippet": snippet,
        }

        try:
            await event_bus.publish(EVENT_ORCHESTRATOR_ERROR, payload)
        except Exception as exc:
            # A subscriber crashing the publish path must not crash the
            # cycle. Log loudly so an operator can find the regression.
            with_context(logger).warning(
                "qa_phrase_post_hook.publish_failed",
                error=str(exc),
                phrase=phrase,
            )
            return

        with_context(logger).warning(
            "qa_phrase_post_hook.match",
            phrase=phrase,
            snippet=snippet,
        )

    return qa_phrase_post_hook


__all__ = [
    "build_qa_phrase_post_hook",
    "scan_for_qa_phrase",
]
