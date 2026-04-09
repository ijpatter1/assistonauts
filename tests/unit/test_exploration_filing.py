"""Tests for exploration filing — saving Explorer answers to wiki/explorations/."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import FakeEmbeddingClient, FakeLLMClient

from assistonauts.agents.explorer import ExplorerAgent, ExplorerResult
from assistonauts.archivist.service import Archivist
from assistonauts.tools.explorer import Citation


@pytest.fixture()
def indexed_workspace(tmp_path: Path) -> Path:
    """Workspace with articles indexed in Archivist DB."""
    ws = tmp_path / "workspace"
    ws.mkdir()
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


class TestExplorationFiling:
    def test_file_exploration_creates_file(self, indexed_workspace: Path) -> None:
        """file_exploration should create a .md file in wiki/explorations/."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        assert path.exists()
        assert "explorations" in str(path)
        assert path.suffix == ".md"

    def test_filed_exploration_has_frontmatter(self, indexed_workspace: Path) -> None:
        """Filed exploration should have YAML frontmatter."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        content = path.read_text()
        assert content.startswith("---\n")
        assert "title:" in content
        assert "type: exploration" in content
        assert "created_at:" in content

    def test_filed_exploration_has_question_section(
        self, indexed_workspace: Path
    ) -> None:
        """Filed exploration should include the original question."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        content = path.read_text()
        assert "## Question" in content
        assert "What are neural networks?" in content

    def test_filed_exploration_has_analysis_section(
        self, indexed_workspace: Path
    ) -> None:
        """Filed exploration should include the answer as analysis."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        content = path.read_text()
        assert "## Analysis" in content

    def test_filed_exploration_has_sources_section(
        self, indexed_workspace: Path
    ) -> None:
        """Filed exploration should list cited articles in Sources."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        content = path.read_text()
        assert "## Sources" in content

    def test_filed_exploration_slug_from_query(self, indexed_workspace: Path) -> None:
        """File name should be a slug derived from the query."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        assert "what-are-neural-networks" in path.stem

    def test_file_exploration_returns_path(self, indexed_workspace: Path) -> None:
        """file_exploration should return the path to the filed exploration."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert isinstance(path, Path)

    def test_file_exploration_with_citations(self, indexed_workspace: Path) -> None:
        """Filed exploration should include citation paths in frontmatter sources."""
        explorer = _make_explorer(indexed_workspace)
        result = explorer.explore("What are neural networks?")
        path = explorer.file_exploration(result)

        assert path is not None
        content = path.read_text()
        # Frontmatter should list source articles
        assert "sources:" in content

    def test_filing_empty_result_still_works(self, indexed_workspace: Path) -> None:
        """Should handle filing a result with no citations gracefully."""
        explorer = _make_explorer(indexed_workspace)
        result = ExplorerResult(
            success=True,
            query="Unknown topic",
            answer="No information available.",
            citations=[],
        )
        path = explorer.file_exploration(result)

        assert path is not None
        assert path.exists()
