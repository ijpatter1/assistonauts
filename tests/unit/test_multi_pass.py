"""Tests for the multi-pass retrieval system."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.archivist.service import Archivist
from assistonauts.rag.multi_pass import (
    MultiPassConfig,
    MultiPassRetriever,
)
from tests.helpers import FakeEmbeddingClient, FakeLLMClient


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

    def test_retrieve_all_four_passes_recorded(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """All four passes should be recorded when retrieval completes."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        assert "pass_1_broad_scan" in result.passes_executed
        assert "pass_2_triage" in result.passes_executed
        assert "pass_3_deep_read" in result.passes_executed
        assert "pass_4_weak_match" in result.passes_executed

    def test_pass_3_tags_deep_read(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Pass 3 should tag articles with deep_read metadata."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        for article in result.articles:
            assert article.get("deep_read") is True

    def test_pass_4_tags_final_pass(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Pass 4 should tag articles with final_pass metadata."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        config = MultiPassConfig(short_circuit_threshold=3)
        retriever = MultiPassRetriever(archivist, embedding_client, config)
        result = retriever.retrieve("spectral analysis")
        for article in result.articles:
            assert article.get("final_pass") is True


class TestMultiPassWithLLM:
    """Test multi-pass retrieval with an LLM client."""

    @pytest.fixture
    def workspace(self, initialized_workspace: Path) -> Path:
        return initialized_workspace

    @pytest.fixture
    def archivist(self, workspace: Path) -> Archivist:
        return Archivist(workspace, embedding_dimensions=4)

    @pytest.fixture
    def embedding_client(self) -> FakeEmbeddingClient:
        return FakeEmbeddingClient(dimensions=4)

    def test_llm_triage_uses_llm_client(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Pass 2 should call the LLM client when one is provided."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        # LLM returns: triage scores, then YES for deep reads
        llm_client = FakeLLMClient(
            responses=[
                "0 0.9\n1 0.7\n2 0.3\n3 0.1\n4 0.05",
                "YES relevant",
                "YES relevant",
                "YES relevant",
                "YES relevant",
                "YES relevant",
            ]
        )
        config = MultiPassConfig(
            short_circuit_threshold=3,
            triage_confidence_threshold=0.3,
        )
        retriever = MultiPassRetriever(
            archivist, embedding_client, config, llm_client=llm_client
        )
        result = retriever.retrieve("spectral analysis")
        assert len(llm_client.calls) > 0  # LLM was called
        assert len(result.articles) > 0

    def test_llm_pass_3_deep_read(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Pass 3 should use LLM to assess full article relevance."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        # First call: triage scores, subsequent calls: YES answers for deep read
        llm_client = FakeLLMClient(
            responses=[
                "0 0.9\n1 0.8\n2 0.7\n3 0.6\n4 0.5",
                "YES relevant to spectral analysis",
                "YES relevant to frequency domain",
                "YES relevant to time series",
                "NO not relevant",
                "NO not relevant",
                # pass 4 won't be called since no borderline candidates
            ]
        )
        config = MultiPassConfig(
            short_circuit_threshold=3,
            triage_confidence_threshold=0.3,
        )
        retriever = MultiPassRetriever(
            archivist, embedding_client, config, llm_client=llm_client
        )
        result = retriever.retrieve("spectral analysis")
        # Should have filtered out rejected articles
        for article in result.articles:
            assert article.get("relevance") != "rejected"

    def test_llm_pass_4_weak_match_resolution(
        self,
        archivist: Archivist,
        workspace: Path,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Pass 4 should resolve borderline matches via LLM."""
        _setup_kb(workspace, archivist, embedding_client, num_articles=5)
        # Triage: give borderline scores to all
        # Deep read: all YES
        # Weak match: include some
        llm_client = FakeLLMClient(
            responses=[
                "0 0.3\n1 0.2\n2 0.1\n3 0.05\n4 0.01",
                "YES somewhat relevant",
                "YES somewhat relevant",
                "YES somewhat relevant",
                "YES somewhat relevant",
                "YES somewhat relevant",
                "0 INCLUDE\n1 INCLUDE\n2 EXCLUDE",
            ]
        )
        config = MultiPassConfig(
            short_circuit_threshold=3,
            triage_confidence_threshold=0.5,  # All will be borderline
        )
        retriever = MultiPassRetriever(
            archivist, embedding_client, config, llm_client=llm_client
        )
        result = retriever.retrieve("spectral analysis")
        assert "pass_4_weak_match" in result.passes_executed
