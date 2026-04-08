"""Tests for the Archivist service — high-level interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.archivist.service import Archivist


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    """Provide an initialized workspace with some wiki articles."""
    return initialized_workspace


@pytest.fixture
def archivist(workspace: Path) -> Archivist:
    """Provide an Archivist instance for testing."""
    return Archivist(workspace, embedding_dimensions=4)


def _write_article(workspace: Path, rel_path: str, content: str) -> Path:
    """Helper to write a wiki article with frontmatter."""
    full_path = workspace / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return full_path


_ARTICLE_A = """\
---
title: Spectral Analysis
type: concept
sources:
  - raw/papers/fft.md
tags:
  - signal-processing
  - mathematics
---

# Spectral Analysis

Spectral analysis is the study of frequency components in signals.

## Key Concepts

Fourier transforms decompose signals into frequency components.

## See Also

- [[frequency-domain]]
"""

_ARTICLE_B = """\
---
title: Frequency Domain
type: concept
sources:
  - raw/papers/signals.md
tags:
  - signal-processing
---

# Frequency Domain

The frequency domain represents signals as sums of sinusoids.
"""


class TestArchivistIndex:
    """Test the index() method — indexing individual articles."""

    def test_index_new_article(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        article = archivist.db.get_article("wiki/concepts/spectral.md")
        assert article is not None
        assert article["title"] == "Spectral Analysis"
        assert article["article_type"] == "concept"

    def test_index_updates_fts(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        results = archivist.db.search_fts("spectral")
        assert len(results) >= 1

    def test_index_stores_content_hash(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        article = archivist.db.get_article("wiki/concepts/spectral.md")
        assert article is not None
        assert len(article["content_hash"]) == 64  # SHA-256 hex

    def test_index_skips_unchanged(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        # Index again — should skip (returns False for no change)
        changed = archivist.index("wiki/concepts/spectral.md")
        assert changed is False

    def test_index_detects_change(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        # Modify the article
        _write_article(
            workspace, "wiki/concepts/spectral.md", _ARTICLE_A + "\nNew content."
        )
        changed = archivist.index("wiki/concepts/spectral.md")
        assert changed is True


class TestArchivistReindexBatch:
    """Test the reindex_batch() method."""

    def test_reindex_batch(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        _write_article(workspace, "wiki/concepts/frequency.md", _ARTICLE_B)
        results = archivist.reindex_batch(
            ["wiki/concepts/spectral.md", "wiki/concepts/frequency.md"]
        )
        assert results["indexed"] == 2
        assert results["skipped"] == 0

    def test_reindex_batch_skips_unchanged(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        results = archivist.reindex_batch(["wiki/concepts/spectral.md"])
        assert results["indexed"] == 0
        assert results["skipped"] == 1


class TestArchivistSearch:
    """Test the search() method — keyword search via FTS."""

    def test_search_finds_article(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        results = archivist.search("spectral analysis")
        assert len(results) >= 1
        assert results[0]["path"] == "wiki/concepts/spectral.md"

    def test_search_no_results(self, archivist: Archivist, workspace: Path) -> None:
        results = archivist.search("nonexistent topic")
        assert len(results) == 0


class TestArchivistStaleness:
    """Test the get_staleness() method."""

    def test_not_stale_after_index(self, archivist: Archivist, workspace: Path) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        staleness = archivist.get_staleness("wiki/concepts/spectral.md")
        assert staleness["is_stale"] is False

    def test_stale_after_modification(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        _write_article(workspace, "wiki/concepts/spectral.md", _ARTICLE_A)
        archivist.index("wiki/concepts/spectral.md")
        _write_article(
            workspace, "wiki/concepts/spectral.md", _ARTICLE_A + "\nModified."
        )
        staleness = archivist.get_staleness("wiki/concepts/spectral.md")
        assert staleness["is_stale"] is True

    def test_staleness_unknown_article(self, archivist: Archivist) -> None:
        staleness = archivist.get_staleness("nonexistent.md")
        assert staleness["is_stale"] is True
        assert staleness["reason"] == "not_indexed"


class TestArchivistDownstream:
    """Test the get_downstream() method."""

    def test_get_downstream_from_manifest(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        """Downstream deps come from the content manifest."""
        from assistonauts.cache.content import Manifest, ManifestEntry

        manifest = Manifest(workspace / "index" / "manifest.json")
        manifest.set(
            "wiki/concepts/spectral.md",
            ManifestEntry(
                hash="abc",
                last_processed="2026-01-01T00:00:00Z",
                processed_by="compiler",
                downstream=["wiki/concepts/frequency.md"],
            ),
        )
        manifest.save()
        # Reload archivist to pick up manifest
        archivist_fresh = Archivist(workspace, embedding_dimensions=4)
        downstream = archivist_fresh.get_downstream("wiki/concepts/spectral.md")
        assert "wiki/concepts/frequency.md" in downstream

    def test_get_downstream_empty(self, archivist: Archivist) -> None:
        downstream = archivist.get_downstream("wiki/concepts/spectral.md")
        assert downstream == []
