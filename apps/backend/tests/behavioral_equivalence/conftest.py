"""vcrpy cassette fixture helpers for behavioural-equivalence tests.

Phase 4.0 gate: this file must exist and ``test_cassette_roundtrip.py``
must pass **before** any other Phase-4 code is written. The harness is the
first thing Phase 4 commits.

All cassettes live in ``apps/backend/tests/behavioral_equivalence/cassettes``
(one YAML per frozen fixture). They record a deterministic stub of the LLM
request/response that the ``agents/think_node`` will replay in Phase 4.5.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import vcr

CASSETTE_DIR: Path = Path(__file__).parent / "cassettes"


def cassette_path(fixture_id: str) -> Path:
    """Return the canonical cassette YAML path for ``fixture_id``.

    Args:
        fixture_id: Frozen-fixture id, e.g. ``"case_13_autopilot_close_full"``.
    """
    return CASSETTE_DIR / f"{fixture_id}.yaml"


def build_vcr(record_mode: str = "none") -> vcr.VCR:
    """Return a vcrpy ``VCR`` instance configured for deterministic replay.

    Args:
        record_mode: ``"none"`` (default, CI) replays only — any unexpected
            HTTP call raises. ``"new_episodes"`` is for local re-recording.

    The cassette library strips auth headers and request bodies on match
    so cassettes are reproducible across environments.
    """
    return vcr.VCR(
        cassette_library_dir=str(CASSETTE_DIR),
        record_mode=record_mode,
        match_on=["method", "scheme", "host", "path"],
        filter_headers=["authorization", "x-api-key", "cookie"],
        decode_compressed_response=True,
    )


@pytest.fixture()
def vcr_cassette_dir() -> Path:
    """Expose the cassette directory to any test that needs to list or stat files."""
    return CASSETTE_DIR


@pytest.fixture()
def build_vcr_factory() -> Iterator[vcr.VCR]:
    """Factory fixture that yields a fresh ``VCR`` instance in replay mode."""
    yield build_vcr(record_mode="none")


def load_cassette_response(fixture_id: str) -> dict[str, Any]:
    """Load a cassette and return the first recorded response body as a dict.

    This is the determinism hook Phase 4.5 uses to compose the frozen LLM
    response directly (without actually going through HTTP) whenever
    vcrpy replay is not convenient.
    """
    import yaml  # local import — yaml ships with vcrpy

    cassette_file = cassette_path(fixture_id)
    if not cassette_file.exists():
        raise FileNotFoundError(f"cassette missing for fixture: {fixture_id}")
    with cassette_file.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    interactions = data.get("interactions") or []
    if not interactions:
        raise ValueError(f"cassette has no interactions: {fixture_id}")
    body_str = interactions[0]["response"]["body"]["string"]
    parsed: Any = json.loads(body_str)
    if not isinstance(parsed, dict):
        raise ValueError(f"cassette body is not a JSON object: {fixture_id}")
    return parsed
