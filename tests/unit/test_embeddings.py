"""Tests for the embedding generation and integration with Archivist."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.archivist.embeddings import (
    chunk_text,
    generate_retrieval_keywords,
)
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeEmbeddingClient


class TestChunking:
    """Test text chunking for embedding generation."""

    def test_short_text_single_chunk(self) -> None:
        chunks = chunk_text("Short text.", max_tokens=100)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_long_text_splits(self) -> None:
        text = " ".join(["word"] * 500)
        chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
        assert len(chunks) > 1
        # Each chunk should be within limit
        for chunk in chunks:
            assert len(chunk.split()) <= 100

    def test_splits_on_paragraph_boundaries(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, max_tokens=5)
        # Should prefer splitting at paragraph breaks
        assert any("First paragraph." in c for c in chunks)

    def test_empty_text(self) -> None:
        chunks = chunk_text("", max_tokens=100)
        assert chunks == []

    def test_overlap_preserves_context(self) -> None:
        words = [f"w{i}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
        # With overlap, consecutive chunks should share some words
        if len(chunks) >= 2:
            first_words = set(chunks[0].split()[-10:])
            second_words = set(chunks[1].split()[:10])
            assert len(first_words & second_words) > 0


class TestRetrievalKeywords:
    """Test deterministic keyword extraction for retrieval summaries."""

    def test_extracts_keywords(self) -> None:
        text = """
        Spectral analysis is a fundamental technique in signal processing.
        It uses the Fourier transform to decompose signals into frequency
        components. The fast Fourier transform (FFT) is an efficient algorithm.
        """
        keywords = generate_retrieval_keywords(text)
        assert len(keywords) > 0
        # Should include significant terms, not stop words
        assert "spectral" in keywords or "fourier" in keywords

    def test_empty_text(self) -> None:
        keywords = generate_retrieval_keywords("")
        assert keywords == []

    def test_deduplicates(self) -> None:
        text = "spectral spectral spectral analysis analysis"
        keywords = generate_retrieval_keywords(text)
        assert len(keywords) == len(set(keywords))


class TestEmbeddingClient:
    """Test the embedding client wrapper."""

    def test_embed_with_fake(self) -> None:
        """FakeEmbeddingClient returns predictable embeddings."""
        client = FakeEmbeddingClient(dimensions=4)
        result = client.embed("test text")
        assert len(result) == 4
        assert all(isinstance(v, float) for v in result)

    def test_embed_batch(self) -> None:
        client = FakeEmbeddingClient(dimensions=4)
        results = client.embed_batch(["text one", "text two"])
        assert len(results) == 2
        assert all(len(r) == 4 for r in results)

    def test_different_text_different_embeddings(self) -> None:
        client = FakeEmbeddingClient(dimensions=4)
        e1 = client.embed("hello world")
        e2 = client.embed("goodbye moon")
        assert e1 != e2


class TestArchivistWithEmbeddings:
    """Test Archivist indexing with embeddings."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    def test_index_with_embeddings(self, archivist: Archivist, workspace: Path) -> None:
        article = workspace / "wiki/concepts/spectral.md"
        article.parent.mkdir(parents=True, exist_ok=True)
        article.write_text(
            "---\ntitle: Spectral\ntype: concept\n---\n\nSpectral analysis of signals."
        )
        client = FakeEmbeddingClient(dimensions=4)
        archivist.index_with_embeddings(
            "wiki/concepts/spectral.md", embedding_client=client
        )
        # Should be searchable via vector
        query_embedding = client.embed("spectral analysis")
        results = archivist.db.search_vec(query_embedding, limit=5)
        assert len(results) >= 1

    def test_index_stores_summary(self, archivist: Archivist, workspace: Path) -> None:
        article = workspace / "wiki/concepts/spectral.md"
        article.parent.mkdir(parents=True, exist_ok=True)
        article.write_text(
            "---\ntitle: Spectral\ntype: concept\n---\n\n"
            "Spectral analysis of signals using Fourier transforms."
        )
        client = FakeEmbeddingClient(dimensions=4)
        archivist.index_with_embeddings(
            "wiki/concepts/spectral.md", embedding_client=client
        )
        summary = archivist.db.get_summary("wiki/concepts/spectral.md")
        assert summary is not None
        assert len(summary["retrieval_keywords"]) > 0

    def test_embedding_cache_skips_unchanged(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        article = workspace / "wiki/concepts/spectral.md"
        article.parent.mkdir(parents=True, exist_ok=True)
        article.write_text("---\ntitle: Spectral\ntype: concept\n---\n\nContent.")
        client = FakeEmbeddingClient(dimensions=4)
        # Index twice
        result1 = archivist.index_with_embeddings(
            "wiki/concepts/spectral.md", embedding_client=client
        )
        result2 = archivist.index_with_embeddings(
            "wiki/concepts/spectral.md", embedding_client=client
        )
        assert result1 is True
        assert result2 is False  # skipped, unchanged
