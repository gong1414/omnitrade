"""SQLiteVecStore — VectorStore implementation backed by sqlite-vec.

Uses the sqlite-vec extension for cosine distance similarity search.
Opens (or creates) a SQLite database at Settings.vector_db_path.
Embedding generation is NOT in this adapter — callers provide embeddings.
"""

from __future__ import annotations

import json
import struct
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

import sqlite_vec
import structlog

from omnitrade.domain.entities import TradingLesson
from omnitrade.observability.trace_context import with_context

logger = structlog.get_logger(__name__)

# Default embedding dimension — must match the embedding model used by callers.
# ADR F-UP 2: pin dim here so drift is caught at init time.
DEFAULT_EMBEDDING_DIM = 1536


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize float list to bytes for sqlite-vec storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _deserialize_embedding(data: bytes) -> list[float]:
    """Deserialize bytes back to float list."""
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


class SQLiteVecStore:
    """VectorStore backed by sqlite-vec for cosine similarity search.

    Args:
        db_path: Path to the SQLite database file.
        embedding_dim: Dimensionality of embedding vectors (default 1536).
    """

    def __init__(self, db_path: str | Path, embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        import sqlite3

        self._db_path = str(db_path)
        self._embedding_dim = embedding_dim
        self._conn = sqlite3.connect(self._db_path)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create the lessons_vec virtual table and metadata table if not exist."""
        self._conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS lessons_meta (
                id TEXT PRIMARY KEY,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                lesson TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                hit_count INTEGER NOT NULL DEFAULT 1,
                market_regime TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS lessons_vec USING vec0(
                id TEXT PRIMARY KEY,
                embedding float[{self._embedding_dim}]
            );
            """
        )
        self._conn.commit()

    async def add(
        self,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> str:
        """Insert a lesson embedding + metadata. Returns the new lesson_id."""
        if len(embedding) != self._embedding_dim:
            raise ValueError(
                f"Embedding dim mismatch: expected {self._embedding_dim}, got {len(embedding)}"
            )
        lesson_id = metadata.get("id") or str(uuid.uuid4())
        with_context(logger).info("sqlite_vec_store.add", lesson_id=lesson_id)

        emb_bytes = _serialize_embedding(embedding)
        meta_json = json.dumps({k: v for k, v in metadata.items() if k != "id"})
        from datetime import datetime

        now_iso = datetime.now(tz=UTC).isoformat()

        self._conn.execute(
            """
            INSERT OR REPLACE INTO lessons_meta
              (id, pattern, action, outcome, lesson, confidence, hit_count,
               market_regime, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lesson_id,
                metadata.get("pattern", text[:200]),
                metadata.get("action", "unknown"),
                metadata.get("outcome", "unknown"),
                metadata.get("lesson", text),
                metadata.get("confidence", 0.5),
                metadata.get("hit_count", 1),
                metadata.get("market_regime", "unknown"),
                metadata.get("created_at", now_iso),
                meta_json,
            ),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO lessons_vec (id, embedding) VALUES (?, ?)",
            (lesson_id, emb_bytes),
        )
        self._conn.commit()
        return lesson_id

    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[tuple[TradingLesson, float]]:
        """Search for top-k most similar lessons by cosine distance.

        Args:
            query_embedding: Query vector (must match embedding_dim).
            k: Number of results to return.
            filter: Optional dict with keys 'market_regime', 'archived'.

        Returns:
            List of (TradingLesson, cosine_distance) tuples, sorted ascending.
        """
        if len(query_embedding) != self._embedding_dim:
            raise ValueError(
                f"Query dim mismatch: expected {self._embedding_dim}, got {len(query_embedding)}"
            )
        with_context(logger).debug("sqlite_vec_store.search", k=k, filter=filter)
        emb_bytes = _serialize_embedding(query_embedding)

        # KNN query using sqlite-vec's vec0 virtual table syntax
        knn_sql = """  # noqa: S608
            SELECT v.rowid, v.distance
            FROM lessons_vec v
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY distance
        """
        try:
            rows = self._conn.execute(knn_sql, (emb_bytes, k)).fetchall()
        except Exception:
            # Fallback: brute-force scan if KNN not supported
            rows = self._conn.execute(
                """
                SELECT id, vec_distance_cosine(embedding, ?) AS dist
                FROM lessons_vec
                ORDER BY dist
                LIMIT ?
                """,
                (emb_bytes, k),
            ).fetchall()

        results: list[tuple[TradingLesson, float]] = []
        for row in rows:
            row_id = row[0]
            distance = float(row[1])
            meta_row = self._conn.execute(
                """SELECT pattern, action, outcome, lesson, confidence, hit_count,
                          market_regime, created_at
                   FROM lessons_meta WHERE id = ?""",
                (str(row_id),),
            ).fetchone()
            if meta_row is None:
                continue
            from datetime import datetime

            try:
                created = datetime.fromisoformat(meta_row[7]).replace(tzinfo=UTC)
            except ValueError:
                created = datetime.now(tz=UTC)
            lesson = TradingLesson(
                id=None,
                pattern=meta_row[0],
                action=meta_row[1],
                outcome=meta_row[2],
                lesson=meta_row[3],
                confidence=__import__("decimal").Decimal(str(meta_row[4])),
                hit_count=int(meta_row[5]),
                market_regime=meta_row[6],
                created_at=created,
            )
            results.append((lesson, distance))
        return results

    async def delete(self, lesson_id: str) -> None:
        """Delete a lesson by ID from both tables."""
        with_context(logger).info("sqlite_vec_store.delete", lesson_id=lesson_id)
        self._conn.execute("DELETE FROM lessons_meta WHERE id = ?", (lesson_id,))
        self._conn.execute("DELETE FROM lessons_vec WHERE id = ?", (lesson_id,))
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
