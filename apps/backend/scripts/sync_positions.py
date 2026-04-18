"""sync_positions.py — Phase 8.6 operational reconciliation CLI.

Reconcile the local ``positions`` table against the exchange's live
``fetch_positions`` view. The exchange is the source of truth; local
rows are overwritten.

Safety gates
------------
- Default mode is ``--dry-run`` — prints the diff, writes nothing.
- ``--apply`` requires ``--yes-really`` AND stdin must be a TTY unless
  ``--non-interactive`` is also passed.
- Non-TTY invocation without ``--apply --yes-really`` exits with code 2.
- Per-row ``Y/n`` prompt confirms each write (skipped with
  ``--non-interactive``).

Exit codes
----------
- ``0`` success (dry-run or apply).
- ``1`` unexpected exception (DB error, exchange error, …).
- ``2`` refused to run — missing safety flags or non-TTY without
  ``--apply --yes-really``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import Any

import structlog

# Package may be invoked either as "python -m omnitrade.scripts.sync_positions"
# or "python apps/backend/scripts/sync_positions.py"; support both by
# appending the backend src/ path when running as a script.
if __package__ in (None, ""):
    import os

    _HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from omnitrade.config import get_settings
from omnitrade.domain.entities import Position
from omnitrade.domain.protocols import ExchangeClient
from omnitrade.infrastructure.persistence.database import build_engines
from omnitrade.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)

logger = structlog.get_logger(__name__)


@dataclass
class PositionDiff:
    """Structured diff between exchange and local positions."""

    only_on_exchange: list[Position]
    only_in_local: list[Position]
    size_mismatch: list[tuple[Position, Position]]  # (exchange, local)

    @property
    def is_empty(self) -> bool:
        return (
            not self.only_on_exchange
            and not self.only_in_local
            and not self.size_mismatch
        )


def compute_diff(
    exchange_positions: list[Position],
    local_positions: list[Position],
) -> PositionDiff:
    """Compute a PositionDiff keyed by (symbol, side).

    Exchange is the authoritative source:
    * present on exchange only → create locally
    * present locally only → delete locally
    * present on both with different quantity → update locally to match
    """
    ex_by_key = {(p.symbol, p.side): p for p in exchange_positions}
    lo_by_key = {(p.symbol, p.side): p for p in local_positions}

    only_on_exchange = [p for k, p in ex_by_key.items() if k not in lo_by_key]
    only_in_local = [p for k, p in lo_by_key.items() if k not in ex_by_key]
    size_mismatch: list[tuple[Position, Position]] = []
    for key, ex_pos in ex_by_key.items():
        lo_pos = lo_by_key.get(key)
        if lo_pos is not None and lo_pos.quantity != ex_pos.quantity:
            size_mismatch.append((ex_pos, lo_pos))

    # Stable orderings for deterministic structlog output.
    only_on_exchange.sort(key=lambda p: (p.symbol, p.side))
    only_in_local.sort(key=lambda p: (p.symbol, p.side))
    size_mismatch.sort(key=lambda t: (t[0].symbol, t[0].side))
    return PositionDiff(
        only_on_exchange=only_on_exchange,
        only_in_local=only_in_local,
        size_mismatch=size_mismatch,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync_positions",
        description="Reconcile local positions table against the exchange (8.6).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print the diff but write nothing (default).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply the diff (requires --yes-really).",
    )
    parser.add_argument(
        "--yes-really",
        action="store_true",
        default=False,
        help="Confirm that --apply is intended (required when --apply is set).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        help="Skip per-row Y/n prompts; valid only with --apply --yes-really.",
    )
    return parser


def _tty_ok() -> bool:
    """True when stdin is attached to a TTY (real interactive terminal)."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _confirm(prompt: str, *, non_interactive: bool) -> bool:
    """Interactive Y/n prompt, default = No. Non-interactive → always yes."""
    if non_interactive:
        return True
    try:
        ans = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans == "y"


async def _apply_diff(
    *,
    diff: PositionDiff,
    repo: PositionRepository,
    session_factory: Any,
    non_interactive: bool,
) -> tuple[int, int, int]:
    """Apply the diff inside one SQLAlchemy transaction.

    Returns (n_created, n_updated, n_deleted).
    """
    n_created = n_updated = n_deleted = 0
    async with session_factory() as session:
        try:
            for ex_pos in diff.only_on_exchange:
                if _confirm(
                    f"Create local {ex_pos.symbol} {ex_pos.side} qty={ex_pos.quantity}",
                    non_interactive=non_interactive,
                ):
                    await repo.create(session, ex_pos)
                    n_created += 1
            for lo_pos in diff.only_in_local:
                if lo_pos.id is None:
                    continue
                if _confirm(
                    f"Delete local {lo_pos.symbol} {lo_pos.side} id={lo_pos.id}",
                    non_interactive=non_interactive,
                ):
                    await repo.delete(session, lo_pos.id)
                    n_deleted += 1
            for ex_pos, lo_pos in diff.size_mismatch:
                if lo_pos.id is None:
                    continue
                if _confirm(
                    f"Update local {lo_pos.symbol} {lo_pos.side} "
                    f"qty {lo_pos.quantity} → {ex_pos.quantity}",
                    non_interactive=non_interactive,
                ):
                    merged = ex_pos.model_copy(update={"id": lo_pos.id})
                    await repo.update(session, merged)
                    n_updated += 1
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return n_created, n_updated, n_deleted


async def run(
    *,
    exchange: ExchangeClient,
    session_factory: Any,
    apply: bool,
    non_interactive: bool,
) -> int:
    """Business logic — returns the CLI exit code."""
    repo = PositionRepository()

    exchange_positions = await exchange.fetch_positions()
    async with session_factory() as session:
        local_positions = await repo.list_all(session)

    diff = compute_diff(exchange_positions, local_positions)
    logger.info(
        "sync_positions.diff",
        exchange_count=len(exchange_positions),
        local_count=len(local_positions),
        only_on_exchange=len(diff.only_on_exchange),
        only_in_local=len(diff.only_in_local),
        size_mismatch=len(diff.size_mismatch),
    )

    # Human-facing textual diff (stdout, so it lands outside the structlog
    # pipeline and is usable for piping / grep).
    print(
        f"Exchange: {len(exchange_positions)} positions | "
        f"Local: {len(local_positions)} positions"
    )
    print(
        f"  only_on_exchange={len(diff.only_on_exchange)}  "
        f"only_in_local={len(diff.only_in_local)}  "
        f"size_mismatch={len(diff.size_mismatch)}"
    )
    for p in diff.only_on_exchange:
        print(f"  + create  {p.symbol} {p.side} qty={p.quantity}")
    for p in diff.only_in_local:
        print(f"  - delete  {p.symbol} {p.side} id={p.id}")
    for ex_p, lo_p in diff.size_mismatch:
        print(
            f"  ~ update  {ex_p.symbol} {ex_p.side} "
            f"qty {lo_p.quantity} → {ex_p.quantity}"
        )

    if not apply:
        print("\n(dry-run mode: nothing was written. Pass --apply --yes-really to apply.)")
        return 0

    if diff.is_empty:
        print("\n(nothing to do — local + exchange already in sync.)")
        return 0

    n_created, n_updated, n_deleted = await _apply_diff(
        diff=diff,
        repo=repo,
        session_factory=session_factory,
        non_interactive=non_interactive,
    )
    logger.info(
        "sync_positions.applied",
        n_created=n_created,
        n_updated=n_updated,
        n_deleted=n_deleted,
    )
    print(
        f"\nApplied: created={n_created} updated={n_updated} deleted={n_deleted}"
    )
    return 0


def _build_exchange_client(settings: Any) -> ExchangeClient:
    """Construct the configured exchange adapter.

    Imported lazily to keep CLI startup fast for --help / dry-run on
    dev boxes that lack the network stack.
    """
    from omnitrade.infrastructure.exchange.ccxt_exchange import CCXTExchange

    if settings.exchange == "gate":
        api_key = settings.gate_api_key.get_secret_value() if settings.gate_api_key else ""
        api_secret = (
            settings.gate_api_secret.get_secret_value() if settings.gate_api_secret else ""
        )
        client: ExchangeClient = CCXTExchange(
            exchange_id="gate",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.gate_use_testnet,
        )
    else:
        api_key = settings.okx_api_key.get_secret_value() if settings.okx_api_key else ""
        api_secret = (
            settings.okx_api_secret.get_secret_value() if settings.okx_api_secret else ""
        )
        passphrase = (
            settings.okx_api_passphrase.get_secret_value()
            if settings.okx_api_passphrase
            else None
        )
        client = CCXTExchange(
            exchange_id="okx",
            api_key=api_key,
            api_secret=api_secret,
            testnet=settings.okx_use_testnet,
            passphrase=passphrase,
        )
    return client


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    _, _, _async_engine, async_factory = build_engines(settings.database_url)
    exchange = _build_exchange_client(settings)
    try:
        return await run(
            exchange=exchange,
            session_factory=async_factory,
            apply=args.apply,
            non_interactive=args.non_interactive,
        )
    finally:
        # Best-effort cleanup; the exchange adapter exposes an ``aclose``
        # on most ccxt paths.
        close = getattr(exchange, "aclose", None)
        if callable(close):
            try:
                await close()
            except Exception:  # noqa: S110 — best-effort teardown
                pass


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Enforce safety contract BEFORE touching DB or exchange.
    if args.apply and not args.yes_really:
        print(
            "error: --apply requires --yes-really (destructive).",
            file=sys.stderr,
        )
        return 2
    if not _tty_ok() and not (args.apply and args.yes_really):
        print(
            "error: non-TTY invocation without --apply --yes-really is refused.",
            file=sys.stderr,
        )
        return 2
    if args.non_interactive and not (args.apply and args.yes_really):
        print(
            "error: --non-interactive requires --apply --yes-really.",
            file=sys.stderr,
        )
        return 2

    try:
        return asyncio.run(_main_async(args))
    except Exception as exc:
        logger.error("sync_positions.failed", error=str(exc), exc_info=True)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


# Re-exports for tests.
__all__ = [
    "PositionDiff",
    "build_parser",
    "compute_diff",
    "main",
    "run",
]
