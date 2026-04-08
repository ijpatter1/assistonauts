"""Tests for enhanced manifest management — embedding versions, staleness."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.archivist.service import Archivist
from assistonauts.cache.content import Manifest, ManifestEntry


class TestManifestLineageTracking:
    """Test full lineage tracking in the manifest."""

    def test_downstream_chain(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.set(
            "raw/papers/fft.md",
            ManifestEntry(
                hash="abc",
                last_processed="2026-01-01T00:00:00Z",
                processed_by="scout",
                downstream=["wiki/concepts/spectral.md"],
            ),
        )
        manifest.set(
            "wiki/concepts/spectral.md",
            ManifestEntry(
                hash="def",
                last_processed="2026-01-01T00:00:00Z",
                processed_by="compiler",
                downstream=["wiki/concepts/frequency.md"],
            ),
        )
        manifest.save()

        # Reload and verify chain
        loaded = Manifest(tmp_path / "manifest.json")
        entry = loaded.get("raw/papers/fft.md")
        assert entry is not None
        assert "wiki/concepts/spectral.md" in entry.downstream

        entry2 = loaded.get("wiki/concepts/spectral.md")
        assert entry2 is not None
        assert "wiki/concepts/frequency.md" in entry2.downstream


class TestArchivistStalenessGraphs:
    """Test staleness detection with downstream dependencies."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    def test_get_stale_articles(self, archivist: Archivist, workspace: Path) -> None:
        """Identify all stale articles in the index."""
        # Create and index two articles
        for name in ["a", "b"]:
            path = workspace / f"wiki/concepts/{name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\ntitle: {name}\ntype: concept\n---\n\nContent {name}."
            )
            archivist.index(f"wiki/concepts/{name}.md")

        # Modify one
        (workspace / "wiki/concepts/a.md").write_text(
            "---\ntitle: a\ntype: concept\n---\n\nUpdated content."
        )

        stale = archivist.get_stale_articles()
        assert "wiki/concepts/a.md" in stale
        assert "wiki/concepts/b.md" not in stale

    def test_get_stale_articles_empty(self, archivist: Archivist) -> None:
        stale = archivist.get_stale_articles()
        assert stale == []

    def test_embedding_version_tracking(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        """Archivist tracks embedding model version in article metadata."""
        path = workspace / "wiki/concepts/test.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\ntitle: Test\ntype: concept\n---\n\nContent.")
        archivist.index("wiki/concepts/test.md")
        archivist.db.upsert_article(
            path="wiki/concepts/test.md",
            title="Test",
            article_type="concept",
            content_hash="abc",
            word_count=1,
        )
        # Set embedding hash
        archivist.db.execute(
            "UPDATE articles SET embedding_hash = ? WHERE path = ?",
            ("model-v1-abc", "wiki/concepts/test.md"),
        )
        article = archivist.db.get_article("wiki/concepts/test.md")
        assert article is not None
        assert article["embedding_hash"] == "model-v1-abc"
