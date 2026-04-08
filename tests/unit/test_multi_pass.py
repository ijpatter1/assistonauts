"""Tests for the multi-pass retrieval system."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.service import Archivist
from assistonauts.rag.multi_pass import (
    MultiPassConfig,
    MultiPassRetriever,
)


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


def _setup_kb(
    workspace: Path,
    archivist: Archivist,
    embedding_client: FakeEmbeddingClient,
    num_articles: int = 5,
) -> None:
    """Populate a knowledge base with test articles."""
    topics = [
        (
            "spectral-analysis",
            "Spectral Analysis",
            "Spectral analysis decomposes signals into "
            "frequency components using Fourier transforms.",
        ),
        (
            "frequency-domain",
            "Frequency Domain",
            "The frequency domain represents signals "
            "as sums of sinusoids and harmonics.",
        ),
        (
            "time-series",
            "Time Series",
            "Time series analysis examines data points collected over time intervals.",
        ),
        (
            "neural-networks",
            "Neural Networks",
            "Neural networks are computational models inspired by biological neurons.",
        ),
        (
            "gradient-descent",
            "Gradient Descent",
            "Gradient descent is an optimization "
            "algorithm for minimizing loss functions.",
        ),
    ]
    for i in range(min(num_articles, len(topics))):
        slug, title, content = topics[i]
        rel_path = f"wiki/concepts/{slug}.md"
        full = f"---\ntitle: {title}\ntype: concept\n---\n\n{content}"
        path = workspace / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(full)
        archivist.index_with_embeddings(rel_path, embedding_client=embedding_client)


class TestMultiPassConfig:
    """Test configuration for multi-pass retrieval."""

    def test_default_config(self) -> None:
        config = MultiPassConfig()
        assert config.short_circuit_threshold > 0
        assert config.short_circuit_word_threshold > 0

    def test_custom_thresholds(self) -> None:
        config = MultiPassConfig(
            short_circuit_threshold=5,
            short_circuit_word_threshold=1000,
        )
        assert config.short_circuit_threshold == 5
        assert config.short_circuit_word_threshold == 1000


class TestShortCircuit:
    """Test short-circuit mode for small knowledge bases."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    @pytest.fixture
    def embedding_client(self) -> FakeEmbeddingClient:
        return FakeEmbeddingClient(dimensions=4)

    def test_short_circuits_small_kb(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Small KB should return all articles directly."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=3)
        config = MultiPassConfig(short_circuit_threshold=10)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        assert result.short_circuited is True
        assert len(result.articles) == 3

    def test_no_short_circuit_large_kb(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Large KB should NOT short-circuit."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        assert result.short_circuited is False


class TestMultiPassRetrieval:
    """Test the full multi-pass retrieval pipeline."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    @pytest.fixture
    def embedding_client(self) -> FakeEmbeddingClient:
        return FakeEmbeddingClient(dimensions=4)

    def test_retrieve_returns_results(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis frequency")
        assert len(result.articles) > 0

    def test_retrieve_includes_paths(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        for article in result.articles:
            assert article["path"].startswith("wiki/")

    def test_retrieve_empty_kb(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        config = MultiPassConfig()
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("anything")
        assert result.short_circuited is True
        assert len(result.articles) == 0

    def test_retrieve_records_passes(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Result should record which passes were executed."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral")
        assert len(result.passes_executed) > 0
        assert "pass_1_broad_scan" in result.passes_executed
