"""Tests for multi-pass retrieval observability."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FakeEmbeddingClient, FakeLLMClient

from assistonauts.archivist.service import Archivist
from assistonauts.rag.multi_pass import MultiPassRetriever, RetrievalLog


@pytest.fixture()
def indexed_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "wiki" / "concept").mkdir(parents=True)
    (ws / "index").mkdir(parents=True)

    for i in range(3):
        article = ws / "wiki" / "concept" / f"article-{i}.md"
        article.write_text(
            f"---\ntitle: Article {i}\ntype: concept\nsources:\n- src.md\n"
            f"created_at: 2026-01-01\n---\n\n## Overview\n\nContent for article {i}.\n"
        )

    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(ws, embedding_dimensions=4)
    for i in range(3):
        archivist.index_with_embeddings(f"wiki/concept/article-{i}.md", embedding)
    return ws


class TestRetrievalLog:
    def test_retrieve_returns_log(self, indexed_workspace: Path) -> None:
        """RetrievalResult should include a RetrievalLog."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("article query")
        assert result.log is not None
        assert isinstance(result.log, RetrievalLog)

    def test_log_has_pass_entries(self, indexed_workspace: Path) -> None:
        """Log should have an entry for each pass executed."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("query")
        assert len(result.log.passes) > 0

    def test_pass_entry_has_name_and_counts(self, indexed_workspace: Path) -> None:
        """Each pass entry should have name, input count, and output count."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("query")
        for entry in result.log.passes:
            assert "name" in entry
            assert "input_count" in entry
            assert "output_count" in entry

    def test_short_circuit_logged(self, indexed_workspace: Path) -> None:
        """Short-circuit should be recorded in the log."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        # 3 articles is under the default threshold of 20
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("query")
        assert result.short_circuited is True
        assert result.log.passes[0]["name"] == "short_circuit"
        assert result.log.passes[0]["output_count"] == 3

    def test_log_records_total_articles(self, indexed_workspace: Path) -> None:
        """Log should record total articles in the knowledge base."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("query")
        assert result.log.total_articles == 3

    def test_log_serializes_to_dict(self, indexed_workspace: Path) -> None:
        """Log should be serializable to a dict for JSON logging."""
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)
        retriever = MultiPassRetriever(archivist=archivist, embedding_client=embedding)

        result = retriever.retrieve("query")
        log_dict = result.log.to_dict()
        assert isinstance(log_dict, dict)
        assert "passes" in log_dict
        assert "total_articles" in log_dict
        assert "query" in log_dict
