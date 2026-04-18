"""LogBuffer — bounded ring + level filter + structlog sidecar wiring."""

from __future__ import annotations

from omnitrade.observability.log_store import LogBuffer, buffer_processor


def test_log_buffer_appends_and_returns_newest_first() -> None:
    buf = LogBuffer(capacity=100)
    for i in range(3):
        buf.append({"event": f"msg-{i}", "level": "info"})

    rows = buf.tail(limit=10)
    assert [r["event"] for r in rows] == ["msg-2", "msg-1", "msg-0"]


def test_log_buffer_enforces_capacity() -> None:
    buf = LogBuffer(capacity=5)
    for i in range(20):
        buf.append({"event": f"msg-{i}", "level": "info"})

    assert len(buf) == 5
    rows = buf.tail(limit=10)
    # Oldest 15 dropped; newest 5 retained, newest-first.
    assert [r["event"] for r in rows] == [f"msg-{i}" for i in range(19, 14, -1)]


def test_log_buffer_level_filter_includes_equal_and_above() -> None:
    buf = LogBuffer(capacity=100)
    buf.append({"event": "d", "level": "debug"})
    buf.append({"event": "i", "level": "info"})
    buf.append({"event": "w", "level": "warning"})
    buf.append({"event": "e", "level": "error"})

    warn_or_above = buf.tail(level="warning", limit=10)
    assert {r["event"] for r in warn_or_above} == {"w", "e"}

    info_or_above = buf.tail(level="info", limit=10)
    assert {r["event"] for r in info_or_above} == {"i", "w", "e"}


def test_log_buffer_level_filter_is_case_insensitive() -> None:
    buf = LogBuffer(capacity=10)
    buf.append({"event": "w", "level": "WARNING"})
    buf.append({"event": "i", "level": "info"})

    rows = buf.tail(level="WARNING", limit=10)
    assert [r["event"] for r in rows] == ["w"]


def test_log_buffer_limit_zero_returns_empty() -> None:
    buf = LogBuffer(capacity=10)
    buf.append({"event": "x", "level": "info"})
    assert buf.tail(limit=0) == []


def test_buffer_processor_is_passthrough_and_mirrors() -> None:
    buf = LogBuffer(capacity=10)
    proc = buffer_processor(buf)

    event = {"event": "hello", "level": "info", "foo": 1}
    returned = proc(None, "info", event)

    # Pass-through: downstream processors still see the original dict.
    assert returned is event
    # Buffer receives an independent copy (snapshot semantics).
    rows = buf.tail(limit=1)
    assert rows[0]["event"] == "hello"
    assert rows[0]["foo"] == 1
