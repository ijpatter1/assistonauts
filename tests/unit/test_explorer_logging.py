"""Tests for Explorer query logging — automatic audit trail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import FakeEmbeddingClient, FakeLLMClient

from assistonauts.agents.explorer import ExplorerAgent
from assistonauts.archivist.service import Archivist


@pytest.fixture()
def indexed_workspace(tmp_path: Path) -> Path:
    """Workspace with articles indexed in Archivist DB."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".assistonauts" / "explorer").mkdir(parents=True)
    (ws / "raw" / "articles").mkdir(parents=True)
    (ws / "wiki" / "concept").mkdir(parents=True)
    (ws / "wiki" / "explorations").mkdir(parents=True)
    (ws / "index").mkdir(parents=True)

    article = ws / "wiki" / "concept" / "neural-networks.md"
    article.write_text(
        "---\ntitle: Neural Networks\ntype: concept\nsources:\n- paper.pdf\n"
        "created_at: 2026-01-01\n---\n\n## Overview\n\nNeural networks.\n\n"
        "## Key Concepts\n\nLayers.\n\n## Sources\n\n- paper.pdf\n"
    )
    summary = ws / "wiki" / "concept" / "neural-networks.summary.json"
    summary.write_text(json.dumps({"summary": "Neural networks overview"}))

    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(ws, embedding_dimensions=4)
    archivist.index_with_embeddings("wiki/concept/neural-networks.md", embedding)
    return ws


def _make_explorer(workspace: Path) -> ExplorerAgent:
    llm = FakeLLMClient(responses=["Neural networks are computing systems."])
    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(workspace, embedding_dimensions=4)
    return ExplorerAgent(
        llm_client=llm,
        workspace_root=workspace,
        archivist=archivist,
        embedding_client=embedding,
    )


class TestExplorerQueryLogging:
    def test_explore_creates_query_log(self, indexed_workspace: Path) -> None:
        """explore() should create a query log file."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("What are neural networks?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        assert log_path.exists()

    def test_query_log_is_valid_jsonl(self, indexed_workspace: Path) -> None:
        """Each line in the log should be valid JSON."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("What are neural networks?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1
        for line in lines:
            entry = json.loads(line)
            assert isinstance(entry, dict)

    def test_log_entry_has_required_fields(self, indexed_workspace: Path) -> None:
        """Log entry must have query, answer, timestamp, and retrieval metadata."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("What are neural networks?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        entry = json.loads(log_path.read_text().splitlines()[0])

        assert entry["query"] == "What are neural networks?"
        assert "answer" in entry
        assert "timestamp" in entry
        assert "citations" in entry
        assert "articles_retrieved" in entry
        assert "articles_used" in entry
        assert "context_tokens_used" in entry

    def test_log_entry_has_citation_details(self, indexed_workspace: Path) -> None:
        """Citations in the log should include title and path."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("What are neural networks?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        entry = json.loads(log_path.read_text().splitlines()[0])

        assert len(entry["citations"]) > 0
        citation = entry["citations"][0]
        assert "title" in citation
        assert "path" in citation

    def test_multiple_queries_append(self, indexed_workspace: Path) -> None:
        """Multiple queries should append to the same log file."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("First question?")
        explorer.explore("Second question?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        lines = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["query"] == "First question?"
        assert second["query"] == "Second question?"

    def test_log_entry_has_retrieval_passes(self, indexed_workspace: Path) -> None:
        """Log entry should record which retrieval passes were executed."""
        explorer = _make_explorer(indexed_workspace)
        explorer.explore("What are neural networks?")

        log_path = indexed_workspace / ".assistonauts" / "explorer" / "queries.jsonl"
        entry = json.loads(log_path.read_text().splitlines()[0])

        assert "passes_executed" in entry
        assert isinstance(entry["passes_executed"], list)

    def test_failed_explore_still_logs(self, indexed_workspace: Path) -> None:
        """Even empty-KB queries should be logged."""
        # Use a workspace with no indexed articles
        ws = indexed_workspace
        llm = FakeLLMClient(responses=["No information available."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(ws, embedding_dimensions=4)
        # Delete the indexed article to simulate empty KB
        archivist.db.delete_article("wiki/concept/neural-networks.md")

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=ws,
            archivist=archivist,
            embedding_client=embedding,
        )
        explorer.explore("Unknown topic?")

        log_path = ws / ".assistonauts" / "explorer" / "queries.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().splitlines()[0])
        assert entry["query"] == "Unknown topic?"
        assert entry["articles_retrieved"] == 0
