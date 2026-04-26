"""Cassette context manager wires vcrpy correctly.

Two layers of test:

1. Passthrough: no path → no error, no interception.
2. Recording: with a real local socket server + real httpx default
   transport, verify vcrpy writes the cassette file and the second
   pass under ``mode='none'`` replays without re-hitting the server.
"""

from __future__ import annotations

import http.server
import os
import socket
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import httpx
import pytest

from omnitrade.backtest.cassette import cassette_context


# Strip proxy env vars before httpx clients construct themselves —
# developer machines often have ALL_PROXY=socks5://... set globally,
# which makes httpx.Client.__init__ raise ImportError when the
# `socksio` extra isn't installed. The cassette tests only ever talk
# to 127.0.0.1, so a proxy would defeat the purpose anyway.
@pytest.fixture(autouse=True)
def _strip_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if "proxy" in key.lower():
            monkeypatch.delenv(key, raising=False)


def test_cassette_disabled_passthrough() -> None:
    """When path is None, the context manager yields without bookkeeping."""
    entered = False
    with cassette_context(None):
        entered = True
    assert entered


@contextmanager
def _local_http_server() -> Iterator[tuple[str, http.server.HTTPServer, list[int]]]:
    """Bind a tiny HTTP server on a free port; tear it down on exit.

    The server tracks the number of requests in ``hit_counter`` so the
    replay test can prove vcrpy never re-hit it.
    """
    hit_counter: list[int] = [0]

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server convention
            hit_counter[0] += 1
            body = b'{"hello": "cassette"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object, **_kwargs: object) -> None:  # noqa: D401
            return None

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", server, hit_counter
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_cassette_records_then_replays(tmp_path: Path) -> None:
    """First pass records into the cassette; second pass under ``none``
    replays from disk and never re-hits the local server.
    """
    cassette_path = tmp_path / "test.yaml"

    with _local_http_server() as (base_url, _server, hit_counter):
        # Pass 1 — record.
        with cassette_context(cassette_path, mode="once"):
            r = httpx.get(f"{base_url}/cassette", timeout=5)
            assert r.status_code == 200
            assert r.json()["hello"] == "cassette"
        assert hit_counter[0] == 1, "first call must hit the live server"
        assert cassette_path.exists(), "cassette file was not written"

        # Pass 2 — strict replay; vcrpy must serve from disk.
        with cassette_context(cassette_path, mode="none"):
            r2 = httpx.get(f"{base_url}/cassette", timeout=5)
            assert r2.status_code == 200
            assert r2.json()["hello"] == "cassette"
        assert hit_counter[0] == 1, "replay must NOT re-hit the live server"


def test_cassette_strict_replay_misses_raise(tmp_path: Path) -> None:
    """``mode='none'`` raises when there's no matching cassette entry."""
    cassette_path = tmp_path / "missing.yaml"
    cassette_path.write_text("interactions: []\nversion: 1\n", encoding="utf-8")

    with pytest.raises(Exception):  # vcrpy raises CannotOverwriteExistingCassetteException
        with cassette_context(cassette_path, mode="none"):
            with _local_http_server() as (base_url, _server, _hits):
                httpx.get(f"{base_url}/missing", timeout=2)
