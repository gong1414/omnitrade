"""GET /sse/stream — Server-Sent Events route smoke test.

End-to-end streaming behaviour (event delivery latency, named-channel
parsing, heartbeat cadence) is validated with a real ``curl -N`` probe
in Docker — see Stage B gate in
``docs/AGNO_MIGRATION_TRACKER.md``. Both Starlette's ``TestClient`` and
httpx's ``ASGITransport`` buffer ``text/event-stream`` chunks, so a
unit-level streaming assertion would just exercise the buffer instead
of the SSE handshake.

Today this file only verifies the route is mounted at ``/sse/stream``
and that the FastAPI app exposes it in its OpenAPI surface.
"""

from __future__ import annotations


def test_sse_stream_route_is_registered(api_app) -> None:  # type: ignore[no-untyped-def]
    """The SSE endpoint must be discoverable in the running FastAPI app."""
    paths = [getattr(route, "path", None) for route in api_app.routes]
    assert "/sse/stream" in paths
