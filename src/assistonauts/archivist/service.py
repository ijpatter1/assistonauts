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
from assistonauts.archivist.embeddings import (
    EmbeddingClient,
    chunk_text,
    generate_retrieval_keywords,
)
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


def _average_embeddings(embeddings: list[list[float]]) -> list[float]:
    """Average multiple embeddings into a single representative vector."""
    if not embeddings:
        return []
    dims = len(embeddings[0])
    avg = [0.0] * dims
    for emb in embeddings:
        for i in range(dims):
            avg[i] += emb[i]
    n = len(embeddings)
    return [v / n for v in avg]


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

        # Load content summary from .summary.json if it exists
        summary_path = full_path.with_suffix(".summary.json")
        if summary_path.exists():
            import json

            data = json.loads(summary_path.read_text())
            content_summary = data.get("summary", "")
            if content_summary:
                self.db.upsert_summary(rel_path, content_summary, "")

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

    def get_stale_articles(self) -> list[str]:
        """Get all indexed articles whose content has changed on disk.

        Returns a list of article paths that need reindexing.
        """
        stale: list[str] = []
        for article in self.db.list_articles():
            path = str(article["path"])
            staleness = self.get_staleness(path)
            if staleness["is_stale"]:
                stale.append(path)
        return stale

    def index_with_embeddings(
        self,
        rel_path: str,
        embedding_client: EmbeddingClient,
    ) -> bool:
        """Index an article with full-text search AND vector embeddings.

        Combines index() with embedding generation and summary extraction.
        Returns True if the article was (re)indexed, False if unchanged.
        """
        full_path = self.workspace / rel_path
        content = full_path.read_text()
        new_hash = _content_hash(content)

        # Check if content has changed since last embedding
        existing = self.db.get_article(rel_path)
        if existing and existing["content_hash"] == new_hash:
            return False

        # Run standard index (metadata + FTS)
        self.index(rel_path)

        # Strip frontmatter for embedding
        body = re.sub(r"^---\n.*?\n---\n?", "", content, count=1, flags=re.DOTALL)

        # Generate and store embedding (average of chunk embeddings)
        chunks = chunk_text(body)
        if chunks:
            chunk_embeddings = embedding_client.embed_batch(chunks)
            avg_embedding = _average_embeddings(chunk_embeddings)
            self.db.upsert_embedding(rel_path, avg_embedding)

            # Store embedding hash so we can detect when re-embedding is needed
            embedding_hash = hashlib.sha256(str(avg_embedding).encode()).hexdigest()[
                :16
            ]
            self.db.set_embedding_hash(rel_path, embedding_hash)

        # Generate and store retrieval keywords
        keywords = generate_retrieval_keywords(body)
        keyword_str = ", ".join(keywords)

        # Load content summary from .summary.json if it exists
        summary_path = full_path.with_suffix(".summary.json")
        content_summary = ""
        if summary_path.exists():
            import json

            data = json.loads(summary_path.read_text())
            content_summary = data.get("summary", "")

        self.db.upsert_summary(rel_path, content_summary, keyword_str)

        return True

    def get_downstream(self, rel_path: str) -> list[str]:
        """Get downstream dependencies from the content manifest.

        Returns paths of articles that depend on the given article.
        """
        entry = self._manifest.get(rel_path)
        if entry is None:
            return []
        return list(entry.downstream)
