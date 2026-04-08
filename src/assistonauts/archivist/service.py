"""Archivist service — deterministic knowledge base operating system.

The Archivist is NOT an agent — it makes no LLM calls. It is a service
that indexes, searches, and tracks staleness of wiki articles using
SQLite (FTS5 + sqlite-vec) and the content manifest.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from assistonauts.archivist.database import ArchivistDB
from assistonauts.cache.content import Manifest


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter fields from markdown text.

    Returns a dict of key-value pairs. Only handles simple scalar values.
    """
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                result[key] = value
    return result


def _word_count(text: str) -> int:
    """Count words in text, excluding frontmatter."""
    # Strip frontmatter
    stripped = re.sub(r"^---\n.*?\n---\n?", "", text, count=1, flags=re.DOTALL)
    return len(stripped.split())


def _content_hash(text: str) -> str:
    """SHA-256 hash of text content."""
    return hashlib.sha256(text.encode()).hexdigest()


class Archivist:
    """Deterministic knowledge base operating system.

    Provides the service interface for indexing, searching, and tracking
    wiki articles. Not an agent — no LLM inference.
    """

    def __init__(
        self,
        workspace: Path,
        embedding_dimensions: int = 384,
    ) -> None:
        self.workspace = Path(workspace)
        self.db = ArchivistDB(
            self.workspace / "index" / "assistonauts.db",
            embedding_dimensions=embedding_dimensions,
        )
        self._manifest = Manifest(self.workspace / "index" / "manifest.json")

    def index(self, rel_path: str) -> bool:
        """Index a single wiki article.

        Reads the article, extracts metadata from frontmatter, updates
        the articles table, and indexes content for FTS.

        Returns True if the article was (re)indexed, False if skipped
        because content hasn't changed.
        """
        full_path = self.workspace / rel_path
        content = full_path.read_text()
        new_hash = _content_hash(content)

        # Check if content has changed
        existing = self.db.get_article(rel_path)
        if existing and existing["content_hash"] == new_hash:
            return False

        frontmatter = _parse_frontmatter(content)
        title = frontmatter.get("title", full_path.stem)
        article_type = frontmatter.get("type", "concept")
        wc = _word_count(content)

        self.db.upsert_article(
            path=rel_path,
            title=title,
            article_type=article_type,
            content_hash=new_hash,
            word_count=wc,
        )

        # Strip frontmatter for FTS indexing
        body = re.sub(r"^---\n.*?\n---\n?", "", content, count=1, flags=re.DOTALL)
        self.db.upsert_fts(rel_path, body)

        return True

    def reindex_batch(self, paths: list[str]) -> dict[str, int]:
        """Reindex a batch of articles.

        Returns a dict with 'indexed' and 'skipped' counts.
        """
        indexed = 0
        skipped = 0
        for path in paths:
            if self.index(path):
                indexed += 1
            else:
                skipped += 1
        return {"indexed": indexed, "skipped": skipped}

    def search(self, query: str, limit: int = 50) -> list[dict[str, object]]:
        """Search articles via FTS keyword search.

        Returns a list of matching articles with path and rank.
        """
        return self.db.search_fts(query, limit=limit)

    def get_staleness(self, rel_path: str) -> dict[str, object]:
        """Check if an article's index entry is stale.

        An article is stale if:
        - It's not in the index at all
        - Its content has changed since last indexing
        """
        existing = self.db.get_article(rel_path)
        if existing is None:
            return {"is_stale": True, "reason": "not_indexed"}

        full_path = self.workspace / rel_path
        if not full_path.exists():
            return {"is_stale": True, "reason": "file_missing"}

        current_hash = _content_hash(full_path.read_text())
        if current_hash != existing["content_hash"]:
            return {
                "is_stale": True,
                "reason": "content_changed",
                "indexed_hash": existing["content_hash"],
                "current_hash": current_hash,
            }

        return {"is_stale": False, "reason": "up_to_date"}

    def get_downstream(self, rel_path: str) -> list[str]:
        """Get downstream dependencies from the content manifest.

        Returns paths of articles that depend on the given article.
        """
        entry = self._manifest.get(rel_path)
        if entry is None:
            return []
        return list(entry.downstream)
