"""Regression lock for cassette format invariants — brand-owned sentinel URL.

Guards the Phase-9.3 cassette-sentinel swap to ``fixtures.omnitrade.test``
(an RFC-2606 reserved TLD that never DNS-resolves). Any future cassette
regeneration that reverts to ``llm.stub.invalid`` or introduces a
different host fails this test.

Also asserts that no cassette still carries a legacy fixture ID prefix
(``snapshot_`` / ``decision_``) — every cassette filename and ``id``
field inside the body must be ``case_NN_*``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from tests.behavioral_equivalence._cassette_synth import CASSETTE_DIR

_EXPECTED_HOST = "fixtures.omnitrade.test"
_REJECTED_HOSTS = {"llm.stub.invalid"}

_CASSETTES = sorted(CASSETTE_DIR.glob("case_*.yaml"))


def test_cassette_directory_holds_only_case_yaml() -> None:
    """All shipping cassettes use the case_ prefix — no snapshot_/decision_ left."""
    all_yaml = sorted(CASSETTE_DIR.glob("*.yaml"))
    # ``_smoke_roundtrip.yaml`` is explicitly carved out by the refresh runbook.
    expected = {p for p in all_yaml if p.stem == "_smoke_roundtrip"} | set(_CASSETTES)
    assert set(all_yaml) == expected, (
        f"unexpected cassettes: {set(all_yaml) - expected}"
    )


@pytest.mark.parametrize("cassette_path", _CASSETTES, ids=[p.stem for p in _CASSETTES])
def test_cassette_request_uri_is_brand_owned(cassette_path: Path) -> None:
    data = yaml.safe_load(cassette_path.read_text())
    for interaction in data["interactions"]:
        uri = interaction["request"]["uri"]
        assert _EXPECTED_HOST in uri, (
            f"{cassette_path.name}: request uri {uri!r} missing brand host {_EXPECTED_HOST!r}"
        )
        for bad in _REJECTED_HOSTS:
            assert bad not in uri, (
                f"{cassette_path.name}: request uri {uri!r} still uses legacy host {bad!r}"
            )


@pytest.mark.parametrize("cassette_path", _CASSETTES, ids=[p.stem for p in _CASSETTES])
def test_cassette_body_ids_carry_case_prefix(cassette_path: Path) -> None:
    data = yaml.safe_load(cassette_path.read_text())
    body_str = data["interactions"][0]["response"]["body"]["string"]
    body = json.loads(body_str)
    # Response top-level id, e.g. chatcmpl-case_01_swingsmith_trailing_L1
    assert re.match(r"^chatcmpl-case_\d{2}_", body["id"]), (
        f"{cassette_path.name}: body.id={body['id']!r} lacks case_NN prefix"
    )
    call_id = body["choices"][0]["message"]["tool_calls"][0]["id"]
    assert re.match(r"^call-case_\d{2}_", call_id), (
        f"{cassette_path.name}: tool_call.id={call_id!r} lacks case_NN prefix"
    )
