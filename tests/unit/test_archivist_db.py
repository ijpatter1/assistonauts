"""Tests for the Archivist database layer — schema creation and low-level ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.archivist.database import ArchivistDB


@pytest.fixture
def db(tmp_path: Path) -> ArchivistDB:
    """Provide a fresh ArchivistDB in a temp directory (4-dim vectors for tests)."""
    return ArchivistDB(tmp_path / "index" / "assistonauts.db", embedding_dimensions=4)


class TestDBInitialization:
    """Verify the database schema is created correctly."""

    def test_creates_db_file(self, db: ArchivistDB) -> None:
        assert db.path.exists()

    def test_creates_articles_table(self, db: ArchivistDB) -> None:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchall()
        assert len(rows) == 1

    def test_creates_fts_table(self, db: ArchivistDB) -> None:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles_fts'"
        ).fetchall()
        assert len(rows) == 1

    def test_creates_vec_table(self, db: ArchivistDB) -> None:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles_vec'"
        ).fetchall()
        assert len(rows) == 1

    def test_creates_summaries_table(self, db: ArchivistDB) -> None:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'"
        ).fetchall()
        assert len(rows) == 1

    def test_idempotent_init(self, tmp_path: Path) -> None:
        """Opening the same DB twice doesn't error."""
        db_path = tmp_path / "index" / "assistonauts.db"
        db1 = ArchivistDB(db_path)
        db1.close()
        db2 = ArchivistDB(db_path)
        rows = db2.execute("SELECT count(*) FROM articles").fetchone()
        assert rows[0] == 0
        db2.close()


class TestArticleCRUD:
    """Test insert, update, and retrieval of article metadata."""

    def test_upsert_article(self, db: ArchivistDB) -> None:
        db.upsert_article(
            path="wiki/concepts/foo.md",
            title="Foo Concept",
            article_type="concept",
            content_hash="abc123",
            word_count=500,
        )
        row = db.execute(
            "SELECT path, title, article_type, content_hash, word_count "
            "FROM articles WHERE path = ?",
            ("wiki/concepts/foo.md",),
        ).fetchone()
        assert tuple(row) == (
            "wiki/concepts/foo.md",
            "Foo Concept",
            "concept",
            "abc123",
            500,
        )

    def test_upsert_updates_existing(self, db: ArchivistDB) -> None:
        db.upsert_article(
            path="wiki/concepts/foo.md",
            title="Foo",
            article_type="concept",
            content_hash="abc",
            word_count=100,
        )
        db.upsert_article(
            path="wiki/concepts/foo.md",
            title="Foo Updated",
            article_type="concept",
            content_hash="def",
            word_count=200,
        )
        row = db.execute(
            "SELECT title, content_hash, word_count FROM articles WHERE path = ?",
            ("wiki/concepts/foo.md",),
        ).fetchone()
        assert tuple(row) == ("Foo Updated", "def", 200)

    def test_get_article(self, db: ArchivistDB) -> None:
        db.upsert_article(
            path="wiki/concepts/foo.md",
            title="Foo",
            article_type="concept",
            content_hash="abc",
            word_count=100,
        )
        article = db.get_article("wiki/concepts/foo.md")
        assert article is not None
        assert article["title"] == "Foo"
        assert article["content_hash"] == "abc"

    def test_get_article_not_found(self, db: ArchivistDB) -> None:
        assert db.get_article("nonexistent.md") is None

    def test_list_articles(self, db: ArchivistDB) -> None:
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_article("wiki/entities/b.md", "B", "entity", "h2", 200)
        articles = db.list_articles()
        assert len(articles) == 2
        paths = {a["path"] for a in articles}
        assert paths == {"wiki/concepts/a.md", "wiki/entities/b.md"}

    def test_delete_article(self, db: ArchivistDB) -> None:
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.delete_article("wiki/concepts/a.md")
        assert db.get_article("wiki/concepts/a.md") is None


class TestFTSOperations:
    """Test FTS5 indexing and search."""

    def test_fts_insert_on_upsert(self, db: ArchivistDB) -> None:
        """Upserting an article also inserts into FTS."""
        db.upsert_article("wiki/concepts/foo.md", "Foo", "concept", "h1", 100)
        db.upsert_fts("wiki/concepts/foo.md", "This is content about spectral analysis")
        rows = db.search_fts("spectral")
        assert len(rows) == 1
        assert rows[0]["path"] == "wiki/concepts/foo.md"

    def test_fts_search_no_results(self, db: ArchivistDB) -> None:
        rows = db.search_fts("nonexistent")
        assert len(rows) == 0

    def test_fts_search_ranking(self, db: ArchivistDB) -> None:
        """Articles with more keyword matches should rank higher."""
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_article("wiki/concepts/b.md", "B", "concept", "h2", 100)
        db.upsert_fts("wiki/concepts/a.md", "spectral analysis of signals")
        db.upsert_fts(
            "wiki/concepts/b.md",
            "spectral analysis spectral methods spectral decomposition",
        )
        rows = db.search_fts("spectral")
        assert len(rows) == 2
        # b should rank higher (more occurrences)
        assert rows[0]["path"] == "wiki/concepts/b.md"

    def test_fts_update(self, db: ArchivistDB) -> None:
        """Updating FTS content replaces old content."""
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_fts("wiki/concepts/a.md", "old content about physics")
        db.upsert_fts("wiki/concepts/a.md", "new content about chemistry")
        assert len(db.search_fts("physics")) == 0
        assert len(db.search_fts("chemistry")) == 1

    def test_fts_delete_on_article_delete(self, db: ArchivistDB) -> None:
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_fts("wiki/concepts/a.md", "spectral analysis")
        db.delete_article("wiki/concepts/a.md")
        assert len(db.search_fts("spectral")) == 0


class TestSummaryOperations:
    """Test dual summary storage."""

    def test_upsert_summary(self, db: ArchivistDB) -> None:
        db.upsert_summary(
            path="wiki/concepts/foo.md",
            content_summary="A comprehensive overview of foo",
            retrieval_keywords="foo, bar, baz",
        )
        summary = db.get_summary("wiki/concepts/foo.md")
        assert summary is not None
        assert summary["content_summary"] == "A comprehensive overview of foo"
        assert summary["retrieval_keywords"] == "foo, bar, baz"

    def test_get_summary_not_found(self, db: ArchivistDB) -> None:
        assert db.get_summary("nonexistent.md") is None

    def test_upsert_summary_updates(self, db: ArchivistDB) -> None:
        db.upsert_summary("wiki/concepts/foo.md", "old summary", "old, keys")
        db.upsert_summary("wiki/concepts/foo.md", "new summary", "new, keys")
        summary = db.get_summary("wiki/concepts/foo.md")
        assert summary is not None
        assert summary["content_summary"] == "new summary"


class TestVecOperations:
    """Test vector embedding storage and similarity search."""

    def test_upsert_embedding(self, db: ArchivistDB) -> None:
        embedding = [0.1, 0.2, 0.3, 0.4]
        db.upsert_embedding("wiki/concepts/foo.md", embedding)
        # Verify it exists by searching
        results = db.search_vec([0.1, 0.2, 0.3, 0.4], limit=1)
        assert len(results) == 1

    def test_search_vec_similarity(self, db: ArchivistDB) -> None:
        """Similar vectors should rank higher."""
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_article("wiki/concepts/b.md", "B", "concept", "h2", 100)
        db.upsert_embedding("wiki/concepts/a.md", [1.0, 0.0, 0.0, 0.0])
        db.upsert_embedding("wiki/concepts/b.md", [0.0, 1.0, 0.0, 0.0])
        # Search for something close to a
        results = db.search_vec([0.9, 0.1, 0.0, 0.0], limit=2)
        assert len(results) == 2
        assert results[0]["path"] == "wiki/concepts/a.md"

    def test_search_vec_with_limit(self, db: ArchivistDB) -> None:
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_article("wiki/concepts/b.md", "B", "concept", "h2", 100)
        db.upsert_embedding("wiki/concepts/a.md", [1.0, 0.0, 0.0, 0.0])
        db.upsert_embedding("wiki/concepts/b.md", [0.0, 1.0, 0.0, 0.0])
        results = db.search_vec([0.5, 0.5, 0.0, 0.0], limit=1)
        assert len(results) == 1

    def test_upsert_embedding_replaces(self, db: ArchivistDB) -> None:
        """Updating an embedding replaces the old one."""
        db.upsert_article("wiki/concepts/a.md", "A", "concept", "h1", 100)
        db.upsert_embedding("wiki/concepts/a.md", [1.0, 0.0, 0.0, 0.0])
        db.upsert_embedding("wiki/concepts/a.md", [0.0, 1.0, 0.0, 0.0])
        # Should find the updated embedding, not the old one
        results = db.search_vec([0.0, 1.0, 0.0, 0.0], limit=1)
        assert results[0]["path"] == "wiki/concepts/a.md"
