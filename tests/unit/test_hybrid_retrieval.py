"""Tests for hybrid retrieval — vector + FTS with reciprocal rank fusion."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.retrieval import (
    hybrid_search,
    reciprocal_rank_fusion,
)
from assistonauts.archivist.service import Archivist


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic embedding client for testing."""

    def __init__(self, dimensions: int = 4) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h[: self._dimensions]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class TestReciprocalRankFusion:
    """Test the RRF reranking algorithm."""

    def test_single_source(self) -> None:
        ranked_lists = [["a", "b", "c"]]
        result = reciprocal_rank_fusion(ranked_lists, k=60)
        assert [r.path for r in result] == ["a", "b", "c"]

    def test_two_sources_agreement(self) -> None:
        """When both sources agree, order is preserved."""
        ranked_lists = [["a", "b", "c"], ["a", "b", "c"]]
        result = reciprocal_rank_fusion(ranked_lists, k=60)
        assert result[0].path == "a"

    def test_two_sources_disagreement(self) -> None:
        """Items appearing in both lists should rank higher."""
        ranked_lists = [["a", "b", "c"], ["d", "b", "e"]]
        result = reciprocal_rank_fusion(ranked_lists, k=60)
        paths = [r.path for r in result]
        # "b" appears in both lists, should rank high
        assert paths.index("b") <= 1

    def test_rrf_scores_decrease(self) -> None:
        ranked_lists = [["a", "b", "c", "d"]]
        result = reciprocal_rank_fusion(ranked_lists, k=60)
        scores = [r.score for r in result]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_empty_lists(self) -> None:
        result = reciprocal_rank_fusion([], k=60)
        assert result == []

    def test_relevance_floor(self) -> None:
        """Results below relevance floor are filtered out."""
        ranked_lists = [["a", "b", "c", "d", "e"]]
        # With k=60, scores are ~0.0164 to ~0.0154. Floor at 0.016 filters most.
        result = reciprocal_rank_fusion(ranked_lists, k=60, relevance_floor=0.016)
        assert len(result) < 5
        assert all(r.score >= 0.016 for r in result)


class TestHybridSearch:
    """Test the hybrid search combining FTS and vector."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    @pytest.fixture
    def embedding_client(self) -> FakeEmbeddingClient:
        return FakeEmbeddingClient(dimensions=4)

    def _write_and_index(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
        rel_path: str,
        title: str,
        content: str,
    ) -> None:
        full = f"---\ntitle: {title}\ntype: concept\n---\n\n{content}"
        path = workspace / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(full)
        archivist.index_with_embeddings(rel_path, embedding_client=embedding_client)

    def test_hybrid_search_finds_article(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        self._write_and_index(
            archivist,
            workspace,
            embedding_client,
            "wiki/concepts/spectral.md",
            "Spectral Analysis",
            "Spectral analysis decomposes signals into frequency components.",
        )
        results = hybrid_search(
            archivist.db,
            query="spectral analysis",
            query_embedding=embedding_client.embed("spectral analysis"),
            limit=10,
        )
        assert len(results) >= 1
        assert any(r.path == "wiki/concepts/spectral.md" for r in results)

    def test_hybrid_search_combines_sources(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """An article found by both FTS and vec should rank higher."""
        self._write_and_index(
            archivist,
            workspace,
            embedding_client,
            "wiki/concepts/spectral.md",
            "Spectral Analysis",
            "Spectral analysis frequency signals Fourier transform.",
        )
        self._write_and_index(
            archivist,
            workspace,
            embedding_client,
            "wiki/concepts/other.md",
            "Other Topic",
            "This article is about completely different things.",
        )
        results = hybrid_search(
            archivist.db,
            query="spectral analysis",
            query_embedding=embedding_client.embed("spectral analysis"),
            limit=10,
        )
        if len(results) >= 2:
            assert results[0].path == "wiki/concepts/spectral.md"

    def test_hybrid_search_no_results(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        results = hybrid_search(
            archivist.db,
            query="nonexistent topic",
            query_embedding=embedding_client.embed("nonexistent topic"),
            limit=10,
        )
        assert len(results) == 0

    def test_hybrid_search_respects_limit(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        for i in range(5):
            self._write_and_index(
                archivist,
                workspace,
                embedding_client,
                f"wiki/concepts/article-{i}.md",
                f"Article {i}",
                f"Content about topic number {i} with analysis.",
            )
        results = hybrid_search(
            archivist.db,
            query="analysis",
            query_embedding=embedding_client.embed("analysis"),
            limit=3,
        )
        assert len(results) <= 3
