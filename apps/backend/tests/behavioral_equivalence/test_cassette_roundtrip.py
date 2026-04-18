"""Phase 4.0 smoke test — record a stub LLM call, replay deterministically.

This test MUST pass before any other Phase-4 file is written. It proves the
vcrpy harness round-trips (record → replay → equal response body).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
import vcr
from vcr.errors import CannotOverwriteExistingCassetteException

from tests.behavioral_equivalence.conftest import build_vcr

SMOKE_CASSETTE_DIR = Path(__file__).parent / "cassettes"
SMOKE_CASSETTE_PATH = SMOKE_CASSETTE_DIR / "_smoke_roundtrip.yaml"


def _write_stub_cassette() -> None:
    """Hand-write a minimal vcrpy cassette for the smoke round-trip test.

    We do not perform a real network call at CI time — we write a canonical
    cassette once, then replay it with ``record_mode="none"``. Any drift in
    the vcrpy library would fail this test.
    """
    SMOKE_CASSETTE_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(
        {
            "id": "smoke-1",
            "model": "stub",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}}],
        }
    )
    cassette_yaml = f"""interactions:
- request:
    method: POST
    uri: https://stub.invalid/v1/chat/completions
    body: '{{}}'
    headers:
      content-type:
      - application/json
  response:
    status:
      code: 200
      message: OK
    headers:
      content-type:
      - application/json
    body:
      string: '{body}'
version: 1
"""
    SMOKE_CASSETTE_PATH.write_text(cassette_yaml, encoding="utf-8")


@pytest.fixture(autouse=True)
def _ensure_smoke_cassette() -> None:
    _write_stub_cassette()


def test_vcr_replay_is_deterministic() -> None:
    """Replay the stub cassette twice and assert the body matches verbatim."""
    my_vcr: vcr.VCR = build_vcr(record_mode="none")

    with my_vcr.use_cassette(str(SMOKE_CASSETTE_PATH)):
        r1 = requests.post("https://stub.invalid/v1/chat/completions", json={}, timeout=5)
    with my_vcr.use_cassette(str(SMOKE_CASSETTE_PATH)):
        r2 = requests.post("https://stub.invalid/v1/chat/completions", json={}, timeout=5)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert r1.json()["choices"][0]["message"]["content"] == "hello"


def test_unknown_request_raises_in_replay_only_mode() -> None:
    """With record_mode='none' a novel URL is a hard error (no silent record)."""
    my_vcr: vcr.VCR = build_vcr(record_mode="none")
    with my_vcr.use_cassette(str(SMOKE_CASSETTE_PATH)):
        with pytest.raises(CannotOverwriteExistingCassetteException):
            requests.get("https://someone-else.invalid/unknown", timeout=5)
