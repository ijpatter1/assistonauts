"""LLM response cache with SQLite backend.

SHA-256 prompt hash keying, configurable TTL, flush per agent/expedition.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def _cache_key(
    model: str,
    system: str | None,
    messages: list[dict[str, str]],
) -> str:
    """Generate a deterministic cache key from request parameters."""
    payload = json.dumps(
        {"model": model, "system": system, "messages": messages},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class LLMResponseCache:
    """SQLite-backed LLM response cache.

    Stores responses keyed by SHA-256(model + system + messages).
    Supports TTL expiration and flush by agent or expedition.
    """

    def __init__(
        self,
        path: Path,
        ttl_seconds: int = 604800,  # 7 days default
        max_size_mb: int = 500,
    ) -> None:
        self.path = Path(path)
        self._ttl_seconds = ttl_seconds
        self._max_size_mb = max_size_mb
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                content TEXT NOT NULL,
                usage TEXT NOT NULL DEFAULT '{}',
                agent TEXT,
                expedition TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_llm_cache_agent
                ON llm_cache(agent);
            CREATE INDEX IF NOT EXISTS idx_llm_cache_expedition
                ON llm_cache(expedition);
        """)
        self._conn.commit()

    def get(
        self,
        model: str,
        system: str | None,
        messages: list[dict[str, str]],
    ) -> dict[str, object] | None:
        """Look up a cached response. Returns None on miss or expiry."""
        key = _cache_key(model, system, messages)
        row = self._conn.execute(
            """
            SELECT content, usage, created_at FROM llm_cache
            WHERE cache_key = ?
            AND datetime(created_at, '+' || ? || ' seconds') > datetime('now')
            """,
            (key, self._ttl_seconds),
        ).fetchone()
        if row is None:
            return None
        return {
            "content": row["content"],
            "usage": json.loads(row["usage"]),
            "created_at": row["created_at"],
        }

    def put(
        self,
        model: str,
        system: str | None,
        messages: list[dict[str, str]],
        content: str,
        usage: dict[str, int],
        agent: str | None = None,
        expedition: str | None = None,
    ) -> None:
        """Store a response in the cache."""
        key = _cache_key(model, system, messages)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO llm_cache
                (cache_key, model, content, usage, agent, expedition, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (key, model, content, json.dumps(usage), agent, expedition),
        )
        self._conn.commit()

    def flush(
        self,
        agent: str | None = None,
        expedition: str | None = None,
    ) -> int:
        """Flush cache entries. Returns number of entries deleted.

        With no args, flushes everything. With agent/expedition, flushes
        only matching entries.
        """
        if agent:
            cursor = self._conn.execute(
                "DELETE FROM llm_cache WHERE agent = ?", (agent,)
            )
        elif expedition:
            cursor = self._conn.execute(
                "DELETE FROM llm_cache WHERE expedition = ?", (expedition,)
            )
        else:
            cursor = self._conn.execute("DELETE FROM llm_cache")
        self._conn.commit()
        return cursor.rowcount

    def stats(self) -> dict[str, object]:
        """Get cache statistics."""
        row = self._conn.execute("SELECT COUNT(*) as total FROM llm_cache").fetchone()
        total = row["total"] if row else 0

        # Approximate size from page_count * page_size
        page_info = self._conn.execute("PRAGMA page_count").fetchone()
        page_size_info = self._conn.execute("PRAGMA page_size").fetchone()
        page_count = page_info[0] if page_info else 0
        page_size = page_size_info[0] if page_size_info else 4096
        size_bytes = page_count * page_size

        return {
            "total_entries": total,
            "total_size_bytes": size_bytes,
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
