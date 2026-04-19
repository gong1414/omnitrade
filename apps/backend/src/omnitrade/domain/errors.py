"""Domain-level errors raised by application services.

Kept under ``domain/`` (not ``application/``) because the invariants these
exceptions encode are intrinsic to the trading model — Alpha Arena's
no-pyramid rule is not an application-plumbing concern, it is a first-class
trading policy that the domain refuses to violate.
"""

from __future__ import annotations


class PyramidViolationError(Exception):
    """Raised when a caller attempts to open a second position in a symbol
    that already has an OPEN position.

    Mirrors Alpha Arena's ``Cannot add to existing positions`` +
    ``Cannot enter new positions in coins already held`` safety net: the
    LLM must CLOSE the existing position before entering a new one.
    The PR-D executor catches this in ``composition._build_execute_fn``
    and returns ``[]`` so the cycle's StructuredReason still records.
    """


__all__ = ["PyramidViolationError"]
