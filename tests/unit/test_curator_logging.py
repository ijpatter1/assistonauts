"""Tests for Curator cross-reference audit trail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistonauts.agents.curator import CuratorAgent
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeEmbeddingClient, FakeLLMClient


@pytest.fixture()
def indexed_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".assistonauts" / "curator").mkdir(parents=True)
    (ws / "wiki" / "concept").mkdir(parents=True)
    (ws / "index").mkdir(parents=True)

    for name, title in [("alpha", "Alpha Concept"), ("beta", "Beta Concept")]:
        article = ws / "wiki" / "concept" / f"{name}.md"
        article.write_text(
            f"---\ntitle: {title}\ntype: concept\nsources:\n- src.md\n"
            f"created_at: 2026-01-01\n---\n\n## Overview\n\nContent about {name}.\n"
        )
        summary = ws / "wiki" / "concept" / f"{name}.summary.json"
        summary.write_text(json.dumps({"summary": f"{title} summary"}))

    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(ws, embedding_dimensions=4)
    archivist.index_with_embeddings("wiki/concept/alpha.md", embedding)
    archivist.index_with_embeddings("wiki/concept/beta.md", embedding)
    return ws


class TestCuratorLogging:
    def test_cross_reference_creates_log(self, indexed_workspace: Path) -> None:
        """cross_reference should create a log file."""
        llm = FakeLLMClient(responses=["WEAK [[beta]]: related topic"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        try:
            curator.cross_reference("wiki/concept/alpha.md")
            log_path = (
                indexed_workspace
                / ".assistonauts"
                / "curator"
                / "cross-references.jsonl"
            )
            assert log_path.exists()
        finally:
            curator.close()

    def test_log_entry_has_required_fields(self, indexed_workspace: Path) -> None:
        """Log entry must have article, candidates, classifications, timestamp."""
        llm = FakeLLMClient(responses=["STRONG [[beta]]: closely related"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        try:
            curator.cross_reference("wiki/concept/alpha.md")
            log_path = (
                indexed_workspace
                / ".assistonauts"
                / "curator"
                / "cross-references.jsonl"
            )
            entry = json.loads(log_path.read_text().splitlines()[0])

            assert entry["article"] == "wiki/concept/alpha.md"
            assert "timestamp" in entry
            assert "candidates_evaluated" in entry
            assert "strong_links" in entry
            assert "weak_links" in entry
            assert "backlinks_added" in entry
        finally:
            curator.close()

    def test_log_records_candidate_slugs(self, indexed_workspace: Path) -> None:
        """Log should record which candidates were evaluated."""
        llm = FakeLLMClient(responses=["WEAK [[beta]]: tangential"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        try:
            curator.cross_reference("wiki/concept/alpha.md")
            log_path = (
                indexed_workspace
                / ".assistonauts"
                / "curator"
                / "cross-references.jsonl"
            )
            entry = json.loads(log_path.read_text().splitlines()[0])

            assert len(entry["candidates_evaluated"]) > 0
            assert any("beta" in c for c in entry["candidates_evaluated"])
        finally:
            curator.close()

    def test_multiple_cross_references_append(self, indexed_workspace: Path) -> None:
        """Multiple cross-reference calls should append to the log."""
        llm = FakeLLMClient(
            responses=["WEAK [[beta]]: related", "WEAK [[alpha]]: related"]
        )
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        try:
            curator.cross_reference("wiki/concept/alpha.md")
            curator.cross_reference("wiki/concept/beta.md")
            log_path = (
                indexed_workspace
                / ".assistonauts"
                / "curator"
                / "cross-references.jsonl"
            )
            lines = [line for line in log_path.read_text().splitlines() if line.strip()]
            assert len(lines) == 2

            first = json.loads(lines[0])
            second = json.loads(lines[1])
            assert first["article"] == "wiki/concept/alpha.md"
            assert second["article"] == "wiki/concept/beta.md"
            # Second entry should have evaluated alpha as a candidate
            assert any("alpha" in c for c in second["candidates_evaluated"])
        finally:
            curator.close()

    def test_log_includes_retrieval_metadata(self, indexed_workspace: Path) -> None:
        """Log should include retrieval pass information."""
        llm = FakeLLMClient(responses=["WEAK [[beta]]: related"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        try:
            curator.cross_reference("wiki/concept/alpha.md")
            log_path = (
                indexed_workspace
                / ".assistonauts"
                / "curator"
                / "cross-references.jsonl"
            )
            entry = json.loads(log_path.read_text().splitlines()[0])

            assert "retrieval" in entry
            assert "passes" in entry["retrieval"]
        finally:
            curator.close()
