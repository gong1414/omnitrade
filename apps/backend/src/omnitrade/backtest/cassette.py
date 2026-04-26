"""HTTP-layer cassette helper for the backtest CLI.

Wraps :func:`vcr.VCR.use_cassette` with a no-op fallback so the CLI
can pass through ``--cassette`` (or ``--no-cassette``) uniformly. The
intercept happens at the httpx transport layer — vcrpy 8.x ships
native httpx support — so every DeepSeek call the Agno Agent makes is
recorded once and replayed on subsequent backtest runs.

Why not :mod:`agno.db` session caching
--------------------------------------
Agno's session DB only persists the high-level run record, not the
per-tool-call HTTP exchange. A backtest cycle issues several DeepSeek
streaming chunks plus tool-result roundtrips — vcrpy is the right
granularity to make replays byte-exact.

Determinism contract
--------------------
* ``record_mode='once'`` (default) — record on first run, replay on
  subsequent runs. New (unseen) requests during replay raise.
* ``record_mode='none'`` — strict replay. Cache misses raise
  ``CannotOverwriteExistingCassetteException`` immediately.
* ``record_mode='all'`` — force re-recording (e.g. after the remote
  API contract changes).
* ``record_mode='new_episodes'`` — replay matched, record unmatched.

Match key & prompt drift
------------------------
The cassette key is built from ``(method, scheme, host, port, path,
query, body)``. ``body`` matters: prompt rendering in production
includes timestamp-bearing fragments (``Recent cycles (most-recent
first)``, ``current_time={iso}``), so two backtests over the **same
candle window** can hash to **different** cache keys even if every
other input is byte-identical. Concretely:

* The first run populates the cassette with whatever prompt the
  engine rendered at that wall clock.
* The second run, ten minutes later, renders a slightly different
  prompt → cache miss → either re-record (``once``/``all``) or raise
  (``none``).

If perfect replay is required, freeze the prompt-relevant timestamps
upstream — for example, run with a fixed :class:`BacktestClock` start
and have ``recent_trades_block`` compute "X cycles ago" only against
that frozen clock. The cassette layer itself does not normalise
prompt content; doing so would risk replaying stale decisions onto
fresh market data.

Authorization headers (and the per-process ``user-agent``) are
filtered out of the cassette payload via ``filter_headers`` so API
keys never end up in git, and re-running with a different key still
hits the same cache entries.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import structlog

logger = structlog.get_logger(__name__)


CassetteMode = Literal["once", "none", "all", "new_episodes"]
"""See :class:`vcr.VCR` — the four record modes that map cleanly to
"warm cache then replay" / "strict replay" / "force re-record" /
"append-on-miss"."""


@contextlib.contextmanager
def cassette_context(
    path: str | Path | None,
    *,
    mode: CassetteMode = "once",
) -> Iterator[None]:
    """Yield inside a vcrpy cassette when ``path`` is set; no-op otherwise.

    Args:
        path: Cassette file. ``None`` disables the cassette entirely
            (live network always hit).
        mode: vcrpy record mode. Default ``"once"`` records on first
            run and replays on subsequent runs. ``"none"`` errors out
            on cache miss.
    """
    if path is None:
        yield
        return

    # Lazy import: tests / non-CLI callers don't need vcrpy in their
    # import graph. The dependency is declared in ``pyproject.toml``.
    import vcr

    cassette_path = Path(path)
    cassette_path.parent.mkdir(parents=True, exist_ok=True)

    vcr_obj = vcr.VCR(
        cassette_library_dir=str(cassette_path.parent),
        record_mode=mode,
        match_on=("method", "scheme", "host", "port", "path", "query", "body"),
        # Headers like User-Agent / Authorization drift between runs;
        # exclude them from the cassette so re-running with a
        # different API key still hits the same key.
        filter_headers=["authorization", "user-agent"],
    )

    logger.info(
        "backtest.cassette.attached",
        path=str(cassette_path),
        mode=mode,
    )
    with vcr_obj.use_cassette(cassette_path.name):
        yield


__all__ = ["CassetteMode", "cassette_context"]
