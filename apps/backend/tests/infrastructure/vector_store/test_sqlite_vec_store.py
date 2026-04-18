"""SQLiteVecStore tests — insert, search, delete, filter.

Protocol compliance: isinstance(store, VectorStore) is True.
Uses an in-memory (temp file) SQLite DB for each test.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from omnitrade.domain.protocols import VectorStore
from omnitrade.infrastructure.vector_store.sqlite_vec_store import SQLiteVecStore

_DIM = 8  # small dim for tests; real embedding_dim is 1536


def _make_store(dim: int = _DIM) -> tuple[SQLiteVecStore, str]:
    """Return (store, path) using a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteVecStore(db_path=path, embedding_dim=dim)
    return store, path


def _random_embedding(dim: int = _DIM, seed: int = 0) -> list[float]:
    import math

    return [math.sin(i + seed) for i in range(dim)]


# ── Protocol compliance ────────────────────────────────────────────────────


def test_sqlite_vec_store_implements_protocol() -> None:
    store, path = _make_store()
    try:
        assert isinstance(store, VectorStore)
    finally:
        store.close()
        os.unlink(path)


# ── Add ───────────────────────────────────────────────────────────────────


async def test_add_returns_id() -> None:
    store, path = _make_store()
    try:
        lesson_id = await store.add(
            text="BTC RSI oversold with volume spike",
            embedding=_random_embedding(seed=1),
            metadata={
                "pattern": "RSI oversold",
                "action": "open_long",
                "outcome": "profitable",
                "lesson": "enter on RSI < 30 + volume",
                "market_regime": "bull",
            },
        )
        assert isinstance(lesson_id, str)
        assert len(lesson_id) > 0
    finally:
        store.close()
        os.unlink(path)


async def test_add_with_explicit_id() -> None:
    store, path = _make_store()
    try:
        lesson_id = await store.add(
            text="test lesson",
            embedding=_random_embedding(seed=2),
            metadata={"id": "custom-id-123", "lesson": "test"},
        )
        assert lesson_id == "custom-id-123"
    finally:
        store.close()
        os.unlink(path)


async def test_add_wrong_dim_raises() -> None:
    store, path = _make_store(dim=4)
    try:
        with pytest.raises(ValueError, match="dim"):
            await store.add(
                text="test",
                embedding=[1.0, 2.0, 3.0],  # wrong dim (3 != 4)
                metadata={},
            )
    finally:
        store.close()
        os.unlink(path)


# ── Delete ────────────────────────────────────────────────────────────────


async def test_delete_removes_lesson() -> None:
    store, path = _make_store()
    try:
        lesson_id = await store.add(
            text="lesson to delete",
            embedding=_random_embedding(seed=3),
            metadata={"id": "del-me", "lesson": "delete test"},
        )
        await store.delete(lesson_id)
        # Verify the row is gone from meta
        row = store._conn.execute(
            "SELECT id FROM lessons_meta WHERE id = ?", (lesson_id,)
        ).fetchone()
        assert row is None
    finally:
        store.close()
        os.unlink(path)


async def test_delete_nonexistent_is_noop() -> None:
    store, path = _make_store()
    try:
        # Should not raise
        await store.delete("does-not-exist")
    finally:
        store.close()
        os.unlink(path)


# ── Search ────────────────────────────────────────────────────────────────


async def test_search_returns_lessons() -> None:
    store, path = _make_store()
    try:
        emb1 = _random_embedding(seed=1)
        emb2 = _random_embedding(seed=5)  # more different
        await store.add(
            text="lesson one",
            embedding=emb1,
            metadata={"lesson": "lesson one", "market_regime": "bull"},
        )
        await store.add(
            text="lesson two",
            embedding=emb2,
            metadata={"lesson": "lesson two", "market_regime": "bear"},
        )
        # Search with emb1 — should find lesson one first (closest)
        results = await store.search(query_embedding=emb1, k=2)
        assert len(results) >= 1
        # Each result is (TradingLesson, float)
        lesson, score = results[0]
        assert lesson.lesson == "lesson one"
        assert isinstance(score, float)
    finally:
        store.close()
        os.unlink(path)


async def test_search_wrong_dim_raises() -> None:
    store, path = _make_store(dim=4)
    try:
        with pytest.raises(ValueError, match="dim"):
            await store.search(query_embedding=[1.0, 2.0], k=1)
    finally:
        store.close()
        os.unlink(path)


async def test_search_empty_store_returns_empty() -> None:
    store, path = _make_store()
    try:
        results = await store.search(query_embedding=_random_embedding(), k=5)
        assert results == []
    finally:
        store.close()
        os.unlink(path)
