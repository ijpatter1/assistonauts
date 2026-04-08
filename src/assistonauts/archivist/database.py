"""Archivist database layer — SQLite with FTS5 and sqlite-vec."""

from __future__ import annotations

import re
import sqlite3
import struct
from pathlib import Path


def _serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float32 vector to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


class ArchivistDB:
    """Low-level database operations for the Archivist.

    Manages the SQLite database with three indexing layers:
    - articles: metadata table for all indexed wiki articles
    - articles_fts: FTS5 virtual table for keyword search
    - articles_vec: sqlite-vec virtual table for vector similarity search
    - summaries: dual summary storage (content + retrieval)
    """

    def __init__(self, path: Path, embedding_dimensions: int = 384) -> None:
        self.path = Path(path)
        self._embedding_dimensions = embedding_dimensions
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._load_extensions()
        self._init_schema()

    def _load_extensions(self) -> None:
        """Load sqlite-vec extension."""
        import sqlite_vec

        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                article_type TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                word_count INTEGER NOT NULL DEFAULT 0,
                indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
                embedding_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS summaries (
                path TEXT PRIMARY KEY,
                content_summary TEXT NOT NULL DEFAULT '',
                retrieval_keywords TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # FTS5 table — separate from articles for clean update semantics
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts
            USING fts5(path, content, tokenize='porter unicode61')
        """)

        # sqlite-vec virtual table for embeddings
        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_vec
            USING vec0(embedding float[{self._embedding_dimensions}])
        """)

        # Mapping from article path to vec rowid
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vec_mapping (
                path TEXT PRIMARY KEY,
                rowid_ref INTEGER NOT NULL UNIQUE
            )
        """)

        self._conn.commit()

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """Execute raw SQL — used by tests for verification."""
        return self._conn.execute(sql, params)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # --- Article CRUD ---

    def upsert_article(
        self,
        path: str,
        title: str,
        article_type: str,
        content_hash: str,
        word_count: int,
    ) -> None:
        """Insert or update an article's metadata."""
        self._conn.execute(
            """
            INSERT INTO articles (
                path, title, article_type, content_hash,
                word_count, indexed_at
            ) VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(path) DO UPDATE SET
                title = excluded.title,
                article_type = excluded.article_type,
                content_hash = excluded.content_hash,
                word_count = excluded.word_count,
                indexed_at = datetime('now')
            """,
            (path, title, article_type, content_hash, word_count),
        )
        self._conn.commit()

    def get_article(self, path: str) -> dict[str, object] | None:
        """Get article metadata by path."""
        row = self._conn.execute(
            "SELECT * FROM articles WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_articles(self) -> list[dict[str, object]]:
        """List all indexed articles."""
        rows = self._conn.execute("SELECT * FROM articles ORDER BY path").fetchall()
        return [dict(r) for r in rows]

    def delete_article(self, path: str) -> None:
        """Delete an article and its associated FTS/vec/summary data."""
        # Delete from FTS
        self._conn.execute("DELETE FROM articles_fts WHERE path = ?", (path,))
        # Delete from vec
        mapping = self._conn.execute(
            "SELECT rowid_ref FROM vec_mapping WHERE path = ?", (path,)
        ).fetchone()
        if mapping:
            self._conn.execute(
                "DELETE FROM articles_vec WHERE rowid = ?", (mapping["rowid_ref"],)
            )
            self._conn.execute("DELETE FROM vec_mapping WHERE path = ?", (path,))
        # Delete summary
        self._conn.execute("DELETE FROM summaries WHERE path = ?", (path,))
        # Delete article
        self._conn.execute("DELETE FROM articles WHERE path = ?", (path,))
        self._conn.commit()

    # --- FTS operations ---

    def upsert_fts(self, path: str, content: str) -> None:
        """Insert or update FTS content for an article."""
        # Delete existing entry if any
        self._conn.execute("DELETE FROM articles_fts WHERE path = ?", (path,))
        self._conn.execute(
            "INSERT INTO articles_fts (path, content) VALUES (?, ?)",
            (path, content),
        )
        self._conn.commit()

    def search_fts(self, query: str, limit: int = 50) -> list[dict[str, object]]:
        """Search articles via FTS5. Returns results ranked by BM25."""
        # Sanitize query: remove FTS5 special characters
        sanitized = re.sub(r"[^\w\s]", " ", query).strip()
        if not sanitized:
            return []
        rows = self._conn.execute(
            """
            SELECT path, rank
            FROM articles_fts
            WHERE articles_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (sanitized, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Summary operations ---

    def upsert_summary(
        self,
        path: str,
        content_summary: str,
        retrieval_keywords: str,
    ) -> None:
        """Insert or update dual summaries for an article."""
        self._conn.execute(
            """
            INSERT INTO summaries (
                path, content_summary, retrieval_keywords, updated_at
            )
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(path) DO UPDATE SET
                content_summary = excluded.content_summary,
                retrieval_keywords = excluded.retrieval_keywords,
                updated_at = datetime('now')
            """,
            (path, content_summary, retrieval_keywords),
        )
        self._conn.commit()

    def get_summary(self, path: str) -> dict[str, object] | None:
        """Get summaries for an article."""
        row = self._conn.execute(
            "SELECT * FROM summaries WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    # --- Vector operations ---

    def _next_vec_rowid(self) -> int:
        """Get the next available rowid for the vec table."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(rowid_ref), 0) + 1 FROM vec_mapping"
        ).fetchone()
        return row[0]  # type: ignore[index] — always returns a row

    def upsert_embedding(self, path: str, embedding: list[float]) -> None:
        """Insert or update a vector embedding for an article."""
        blob = _serialize_f32(embedding)

        # Check if mapping exists
        existing = self._conn.execute(
            "SELECT rowid_ref FROM vec_mapping WHERE path = ?", (path,)
        ).fetchone()

        if existing:
            # Delete old embedding, insert new one at same rowid
            rowid = existing["rowid_ref"]
            self._conn.execute("DELETE FROM articles_vec WHERE rowid = ?", (rowid,))
            self._conn.execute(
                "INSERT INTO articles_vec (rowid, embedding) VALUES (?, ?)",
                (rowid, blob),
            )
        else:
            rowid = self._next_vec_rowid()
            self._conn.execute(
                "INSERT INTO articles_vec (rowid, embedding) VALUES (?, ?)",
                (rowid, blob),
            )
            self._conn.execute(
                "INSERT INTO vec_mapping (path, rowid_ref) VALUES (?, ?)",
                (path, rowid),
            )

        self._conn.commit()

    def search_vec(
        self, query_embedding: list[float], limit: int = 20
    ) -> list[dict[str, object]]:
        """Search for similar articles by vector distance."""
        blob = _serialize_f32(query_embedding)
        rows = self._conn.execute(
            """
            SELECT v.rowid, v.distance, m.path
            FROM articles_vec v
            JOIN vec_mapping m ON m.rowid_ref = v.rowid
            WHERE v.embedding MATCH ?
            AND k = ?
            ORDER BY v.distance
            """,
            (blob, limit),
        ).fetchall()
        return [dict(r) for r in rows]
